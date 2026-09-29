from pathlib import Path

import pytest

from ema.audit.headings import Heading, HeadingMap, MappedHeading, select_profile


def _outline(sections: list[str], old: int = 0) -> HeadingMap:
    headings = tuple(
        MappedHeading(Heading(1, section, (), index), section)
        for index, section in enumerate(sections)
    )
    old_headings = tuple((Heading(1, "older", (), index), "older layout") for index in range(old))
    return HeadingMap(headings, (), old_headings, ())


def test_selects_base_from_structural_headings() -> None:
    sections = ["ch2"] * 36 + ["ch3.process"] * 2 + ["ch6.measure"] * 5 + ["ch6"] * 5
    sections.extend(["ch3"] * 5)
    assert select_profile(_outline(sections), Path("renamed.docx")) == "audit-01"


def test_empty_outline_reports_file_and_scores() -> None:
    with pytest.raises(ValueError, match=r"renamed.docx: scores="):
        select_profile(_outline([]), Path("renamed.docx"))


def test_tied_profile_reports_scores() -> None:
    sections = ["ch6.measure"] * 3 + ["ch6"] * 2
    with pytest.raises(ValueError, match=r"tied.docx: scores="):
        select_profile(_outline(sections), Path("tied.docx"))


def test_unrelated_outline_has_no_profile() -> None:
    with pytest.raises(ValueError, match=r"unrelated.docx: scores="):
        select_profile(_outline(["ch2"] * 12), Path("unrelated.docx"))
