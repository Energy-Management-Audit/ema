"""Source-inspected differences from legacy ALIVE OCR; values are pinned by digest.

Page renders and the value-level audit live outside git in
EMA_ARTIFACTS/s9b/alive-exceptions/. Each row identifies the changed field or
zero-based price ordinal. No client values belong in this module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceException:
    page: int
    category: str
    reason: str
    digest: str


ALIVE_PINS: dict[tuple[str, str], SourceException] = {
    ("01.2024 Adv.pdf", "price6"): SourceException(
        1,
        "legacy-misread",
        "Legacy OCR inserted a letter in the printed charge name.",
        "84fd4aa636c437c37d5c",
    ),
    ("02.2024 Final.pdf", "price_count"): SourceException(
        2,
        "legacy-omitted-row",
        "Legacy missed two printed charges on page 2.",
        "4ec9599fc203d176a301",
    ),
    ("02.2024 Final.pdf", "price9"): SourceException(
        2,
        "legacy-omitted-row",
        "Printed network injection charge was omitted by legacy.",
        "5aa6eac3221765b2cd96",
    ),
    ("02.2024 Final.pdf", "price10"): SourceException(
        2,
        "legacy-omitted-row",
        "Legacy row alignment shifted after its omitted charge.",
        "7da68911e35a3cec2e68",
    ),
    ("02.2024 Final.pdf", "price11"): SourceException(
        2,
        "legacy-omitted-row",
        "Legacy row alignment shifted after its omitted charge.",
        "391cc1f4de48472349b2",
    ),
    ("02.2024 Final.pdf", "price12"): SourceException(
        2,
        "legacy-omitted-row",
        "Printed distribution charge was omitted by legacy.",
        "afe1e66676eb103f74ce",
    ),
    ("02.2024 Final.pdf", "price13"): SourceException(
        2,
        "legacy-omitted-row",
        "Legacy row alignment shifted after two omitted charges.",
        "076e26dd28c74a509685",
    ),
    ("02.2024 Final.pdf", "price14"): SourceException(
        2,
        "legacy-omitted-row",
        "Legacy row alignment shifted after two omitted charges.",
        "fc446fa3899e57beb824",
    ),
    ("02.2024 Final.pdf", "price15"): SourceException(
        2,
        "legacy-omitted-row",
        "Legacy row alignment shifted after two omitted charges.",
        "221d621233f5746b45b4",
    ),
    ("03.2024 Adv.pdf", "price6"): SourceException(
        1,
        "other",
        "Printed unaccented charge name differs from legacy OCR normalization.",
        "d69f966b26da983251fc",
    ),
    ("03.2024 Final.pdf", "reactive_capacitive"): SourceException(
        4,
        "legacy-misread",
        "Equal printed meter indexes give zero; legacy read a scan artifact.",
        "8ea94e475a20ff4b0883",
    ),
    ("03.2024 Final.pdf", "price10"): SourceException(
        2,
        "legacy-misread",
        "Legacy OCR inserted a leading mark before the printed charge.",
        "3e7a15681fb5fc1e480e",
    ),
    ("03.2024 Final.pdf", "price14"): SourceException(
        2,
        "legacy-misread",
        "Legacy OCR misread the printed unit price and amount.",
        "33a539b408b6a537a63e",
    ),
    ("03.2024 Final.pdf", "price17"): SourceException(
        4,
        "legacy-misread",
        "Equal printed meter indexes give zero; legacy read a scan artifact.",
        "60a045614a96baf6c542",
    ),
    ("04.2024.pdf", "price6"): SourceException(
        1,
        "legacy-misread",
        "Legacy OCR inserted a letter in the printed charge name.",
        "6cdfba539981681770f9",
    ),
    ("05.2024.pdf", "price_count"): SourceException(
        1,
        "legacy-misread",
        "Legacy duplicated a printed charge after an OCR misspelling.",
        "4a44dc15364204a80fe8",
    ),
    ("05.2024.pdf", "price6"): SourceException(
        1,
        "legacy-misread",
        "Legacy OCR inserted a letter in the printed charge name.",
        "9d60020149793b400d56",
    ),
    ("05.2024.pdf", "price8"): SourceException(
        3,
        "legacy-misread",
        "Legacy duplicate shifted the printed meter-reading row.",
        "90d5d0a9009963570775",
    ),
    ("05.2024.pdf", "price9"): SourceException(
        3,
        "legacy-misread",
        "Legacy duplicate shifted the printed meter-reading row.",
        "19cdcca47bf478c867e1",
    ),
    ("07.2024.pdf", "price6"): SourceException(
        1,
        "other",
        "Current price is printed; legacy recalculated excess precision.",
        "173a9dd02423c94fea43",
    ),
    ("09.2024.pdf", "price7"): SourceException(
        1,
        "legacy-misread",
        "Legacy OCR misread one digit of the printed amount.",
        "617712b84b2af8f21dbf",
    ),
    ("10.2024.pdf", "price6"): SourceException(
        1,
        "other",
        "Current price is printed; legacy recalculated excess precision.",
        "0962d58ba0e65dcf2abc",
    ),
}


ENGIE_PINS: dict[tuple[str, str], SourceException] = {
    ("8. August.pdf", "price_count"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy merged a printed CfD charge into the preceding description.",
        "2c624232cdd221771294",
    ),
    ("8. August.pdf", "price5"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy appended CfD text to the preceding charge.",
        "725bf33f9a448a3cf93d",
    ),
    ("8. August.pdf", "price6"): SourceException(
        4,
        "legacy-omitted-row",
        "Printed CfD charge is a separate billed row.",
        "9f4bf1d1a5d2da3e2fb4",
    ),
    ("8. August_1.pdf", "price_count"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy merged a printed CfD charge into the preceding description.",
        "2c624232cdd221771294",
    ),
    ("8. August_1.pdf", "price5"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy appended CfD text to the preceding charge.",
        "076ff6377f144b6ad2b1",
    ),
    ("8. August_1.pdf", "price6"): SourceException(
        4,
        "legacy-omitted-row",
        "Printed CfD charge is a separate billed row.",
        "dbffa8bc2e40b7f5d532",
    ),
    ("9. Septembrie_1.pdf", "price_count"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy merged a printed CfD charge into the preceding description.",
        "2c624232cdd221771294",
    ),
    ("9. Septembrie_1.pdf", "price5"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy appended CfD text to the preceding charge.",
        "432a1668cb747e57a5ec",
    ),
    ("9. Septembrie_1.pdf", "price6"): SourceException(
        4,
        "legacy-omitted-row",
        "Printed CfD charge is a separate billed row.",
        "f868f1ff9b65ff18b2d7",
    ),
    ("10. Octombrie_1.pdf", "price_count"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy merged a printed CfD charge into the preceding description.",
        "2c624232cdd221771294",
    ),
    ("10. Octombrie_1.pdf", "price5"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy appended CfD text to the preceding charge.",
        "0f210c268add8f9f8b7d",
    ),
    ("10. Octombrie_1.pdf", "price6"): SourceException(
        4,
        "legacy-omitted-row",
        "Printed CfD charge is a separate billed row.",
        "42a53854b51d0f7ecf46",
    ),
    ("11. Noiembrie_1.pdf", "price_count"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy merged a printed CfD charge into the preceding description.",
        "2c624232cdd221771294",
    ),
    ("11. Noiembrie_1.pdf", "price5"): SourceException(
        4,
        "legacy-omitted-row",
        "Legacy appended CfD text to the preceding charge.",
        "fc21c0479232912b88cf",
    ),
    ("11. Noiembrie_1.pdf", "price6"): SourceException(
        4,
        "legacy-omitted-row",
        "Printed CfD charge is a separate billed row.",
        "20e468fdd25276a805dd",
    ),
}
