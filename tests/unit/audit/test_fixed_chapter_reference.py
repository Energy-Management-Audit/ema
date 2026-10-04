"""Only the funding chapter reference may follow rendered numbering."""

from tests.golden.test_s10b_audit_base import _renumbered_chapter_reference


def test_chapter_reference_accepts_only_the_rendered_number() -> None:
    source = "Finanțarea conform Capitolului 7."
    assert _renumbered_chapter_reference(source, "Finanțarea conform Capitolului 6.", "6")
    assert not _renumbered_chapter_reference(source, "Finanțarea conform Capitolului 5.", "6")
    assert not _renumbered_chapter_reference(source, "Altă finanțare conform Capitolului 6.", "6")
    assert not _renumbered_chapter_reference(
        "Capitolului 7 și Capitolului 7", "Capitolului 6 și Capitolului 6", "6"
    )
