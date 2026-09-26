"""Intake-only agent tools with explicit evidence checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from ema.core.errors import EmaError
from ema.core.llm.agent import Tool
from ema.core.llm.types import ToolSpec


@dataclass(frozen=True)
class IntakeDocument:
    name: str
    text: str = ""
    ocr_text: str = ""
    page_images: tuple[str, ...] = ()


@dataclass
class IntakeTools:
    documents: dict[str, IntakeDocument]
    checklist: dict[int, str]
    classifications: dict[str, int] = field(default_factory=dict[str, int])
    evidence: dict[str, str] = field(default_factory=dict[str, str])
    missing: set[int] = field(default_factory=set[int])

    def list_files(self, args: dict[str, Any]) -> object:
        del args
        return sorted(self.documents)

    def read_file(self, args: dict[str, Any]) -> object:
        name = str(args["name"])
        document = self.documents.get(name)
        if document is None:
            raise EmaError("file_missing", "Fişierul cerut lipseşte.", name)
        return {
            "text": document.text,
            "ocr_text": document.ocr_text,
            "page_images": document.page_images,
        }

    def classify_file(self, args: dict[str, Any]) -> object:
        name, number, quote = str(args["name"]), int(args["item"]), str(args["quote"])
        document = self.documents.get(name)
        if document is None or number not in self.checklist:
            raise EmaError("classification_invalid", "Clasificarea nu este validă.", name)
        if not quote or (quote not in document.text and quote not in document.ocr_text):
            raise EmaError("evidence_quote", "Fragmentul citat nu apare în fişier.", name)
        self.classifications[name] = number
        self.evidence[name] = quote
        self.missing.discard(number)
        return {"classified": name, "item": number, "quote": quote}

    def mark_missing(self, args: dict[str, Any]) -> object:
        number = int(args["item"])
        if number not in self.checklist:
            raise EmaError("checklist_item", "Poziţia din listă nu există.", str(number))
        if number not in self.classifications.values():
            self.missing.add(number)
        return {"missing": number}

    def restore(self, messages: list[dict[str, Any]]) -> None:
        for message in messages:
            if message["role"] != "tool":
                continue
            result = message["content"]
            if not isinstance(result, dict):
                continue
            values = cast(dict[str, object], result)
            name, item, quote = values.get("classified"), values.get("item"), values.get("quote")
            if isinstance(name, str) and isinstance(item, int) and isinstance(quote, str):
                self.classifications[name] = item
                self.evidence[name] = quote
                self.missing.discard(item)
            elif isinstance(values.get("missing"), int):
                self.missing.add(cast(int, values["missing"]))

    def tools(self) -> dict[str, Tool]:
        string = {"type": "string"}
        integer = {"type": "integer"}
        return {
            "list_files": Tool(
                ToolSpec(
                    "list_files", "List dossier file names", {"type": "object", "properties": {}}
                ),
                self.list_files,
            ),
            "read_file": Tool(
                ToolSpec(
                    "read_file",
                    "Read text, OCR and page image references",
                    {"type": "object", "properties": {"name": string}, "required": ["name"]},
                ),
                self.read_file,
            ),
            "classify_file": Tool(
                ToolSpec(
                    "classify_file",
                    "Classify with a verbatim text quote",
                    {
                        "type": "object",
                        "properties": {"name": string, "item": integer, "quote": string},
                        "required": ["name", "item", "quote"],
                    },
                ),
                self.classify_file,
            ),
            "mark_missing": Tool(
                ToolSpec(
                    "mark_missing",
                    "Record a missing checklist item",
                    {"type": "object", "properties": {"item": integer}, "required": ["item"]},
                ),
                self.mark_missing,
            ),
        }
