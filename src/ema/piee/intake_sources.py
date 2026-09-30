"""Map PIEE source identifiers to their stored file checksums."""

from typing import Literal

Method = Literal["questionnaire", "anexa", "prelucrare", "calc"]


def method(source: str) -> Method:
    if source.startswith("prelucrare"):
        return "prelucrare"
    if source == "anexa":
        return "anexa"
    if source in {"calculated", "carrier_sum"}:
        return "calc"
    return "questionnaire"


def file(source: str, shas: dict[str, str | None]) -> str | None:
    return shas.get(method(source))
