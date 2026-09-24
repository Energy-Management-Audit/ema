"""Extract anonymous wording patterns from the approved reference set."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from docx import Document

from ema.core.resources import resource_path

SOURCES = {
    "audit-01": "audit/finished-audits/*AUDIT-01*.docx",
    "audit-02": "audit/finished-audits/*AUDIT-02*.docx",
    "audit-03": "audit/finished-audits/*AUDIT-03*.docx",
    "audit-04": "audit/finished-audits/*AUDIT-04*.docx",
    "audit-05": "audit/finished-audits/Cap 2-3-4 V2.docx",
    "piee-01": "piee/**/*MODEL_2026.docx",
    "piee-02": "piee/**/*CLIENT-P2*FINAL V4.docx",
    "piee-03": "piee/**/*CLIENT-P1 SA_2026.docx",
}
TREND_EVIDENCE = {
    "growth": (("audit-01", 838), ("audit-01", 843), ("audit-02", 694)),
    "decline": (("audit-01", 848), ("audit-01", 859), ("audit-02", 777)),
    "constant": (("piee-03", 135),),
}
CLIENT_WORDS = (
    "AUDIT-01",
    "AUDIT-02",
    "AUDIT-03",
    "AUDIT-04",
    "AUDIT-04",
    "AUDIT-05",
    "CLIENT-I5",
    "CLIENT-P2",
    "CLIENT-P1",
)
NUMBER = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)")
FIGURE_NUMBER = re.compile(r"(?i)(Conform figurii numărul\s+)\d+(?:\.\d+)?")
YEAR = re.compile(r"(?<!\d)20\d{2}(?!\d)")
TREND = re.compile(r"(?:tendinț[ăa]|s-a menținut constant[ăa]|evoluție fluctuantă)", re.I)
FIGURE = re.compile(r"(?:Conform figurii numărul|În perioada analizată,)", re.I)
VALUE_BULLET = re.compile(
    r"(?i)^pentru anul 20\d{2} (?:s-a înregistrat o valoare de|s-au înregistrat) "
)


def _pattern(text: str) -> str:
    text = " ".join(text.split())
    text = FIGURE_NUMBER.sub(r"\g<1>{figure_number}", text)
    text = YEAR.sub("{year}", text)
    text = NUMBER.sub("{number}", text)
    return text


def _category(text: str) -> str:
    folded = text.casefold()
    if "constant" in folded:
        return "constant"
    if "creștere" in folded:
        return "growth"
    if "scădere" in folded:
        return "decline"
    return "fluctuating"


def extract(root: Path) -> list[dict[str, str | int]]:
    patterns: list[dict[str, str | int]] = []
    for source, glob in SOURCES.items():
        matches = list(root.glob(glob))
        if len(matches) != 1:
            raise ValueError(f"{source}: expected one source document, got {len(matches)}")
        for index, paragraph in enumerate(Document(matches[0]).paragraphs):
            text = " ".join(paragraph.text.split())
            if not ((TREND.search(text) and FIGURE.match(text)) or VALUE_BULLET.match(text)):
                continue
            if "relativ constant" in text.casefold():
                continue
            if any(word.casefold() in text.casefold() for word in CLIENT_WORDS):
                continue
            if len(text) > 420:
                continue
            patterns.append(
                {
                    "source_document": source,
                    "paragraph": index,
                    "direction": "value" if VALUE_BULLET.match(text) else _category(text),
                    "pattern": _pattern(text) + (" " if paragraph.text.endswith(" ") else ""),
                }
            )
    if {item["source_document"] for item in patterns} != set(SOURCES):
        raise ValueError("Every reference source must contribute a safe wording pattern")
    return patterns


def main() -> None:
    root = Path(os.environ["EMA_REFERENCE"])
    output = resource_path("consumption_analysis", "phrases.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    patterns = extract(root)
    output.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in patterns),
        encoding="utf-8",
    )
    rules = {
        "method": "least_squares_slope",
        "rounding": "ROUND_HALF_UP to the source prototype's displayed decimals first",
        "growth": "rounded slope > 0",
        "decline": "rounded slope < 0",
        "constant": "rounded slope == 0",
        "source_references": {
            direction: [
                {"source_document": source, "paragraph": index} for source, index in references
            ]
            for direction, references in TREND_EVIDENCE.items()
        },
    }
    resource_path("consumption_analysis", "trend_rules.json").write_text(
        json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(patterns)} patterns from {len(SOURCES)} documents")


if __name__ == "__main__":
    main()
