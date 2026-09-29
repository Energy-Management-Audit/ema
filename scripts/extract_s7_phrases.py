"""Extract anonymous wording patterns from the approved reference set."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from docx import Document
from tests.golden.cases import case_path, private_terms

from ema.core.resources import resource_path

SOURCES = {
    "audit-01": case_path("audit-01"),
    "audit-02": case_path("audit-02"),
    "audit-03": case_path("audit-03"),
    "audit-04": case_path("audit-04"),
    "audit-05": case_path("audit-05"),
    "piee-01": case_path("piee-01"),
    "piee-02": case_path("piee-02"),
    "piee-03": case_path("piee-03"),
}
TREND_EVIDENCE = {
    "growth": (("audit-01", 838), ("audit-01", 843), ("audit-02", 694)),
    "decline": (("audit-01", 848), ("audit-01", 859), ("audit-02", 777)),
    "constant": (("piee-03", 135),),
}
CLIENT_WORDS = private_terms()
ALLOWED_CAPITAL_WORDS = frozenset({"Conform", "În", "Curba", "Consumul", "Valoarea", "MWh", "SEN"})
CAPITAL_WORD = re.compile(r"(?<!\w)[A-ZĂÂÎȘȚŞŢ][\w-]*")


def safe_pattern(text: str) -> bool:
    return all(word in ALLOWED_CAPITAL_WORDS for word in CAPITAL_WORD.findall(text))


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
    for source, path in SOURCES.items():
        for index, paragraph in enumerate(Document(path).paragraphs):
            text = " ".join(paragraph.text.split())
            if not ((TREND.search(text) and FIGURE.match(text)) or VALUE_BULLET.match(text)):
                continue
            if "relativ constant" in text.casefold():
                continue
            if any(word.casefold() in text.casefold() for word in CLIENT_WORDS):
                continue
            if len(text) > 420:
                continue
            pattern = _pattern(text) + (" " if paragraph.text.endswith(" ") else "")
            if not safe_pattern(pattern):
                continue
            patterns.append(
                {
                    "source_document": source,
                    "paragraph": index,
                    "direction": "value" if VALUE_BULLET.match(text) else _category(text),
                    "pattern": pattern,
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
