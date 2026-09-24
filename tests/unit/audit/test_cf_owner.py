"""Land-registry CIF selection needs matching owner name and one unique value."""

from pathlib import Path

import pytest

from ema.audit import cf_owner
from ema.core.errors import EmaError


class Page:
    def __init__(self, text: str) -> None:
        self.text = text

    def get_textpage(self) -> "Page":
        return self

    def get_text_range(self) -> str:
        return self.text


class Document:
    def __init__(self, _: Path, text: str) -> None:
        self.text = text

    def __len__(self) -> int:
        return 1

    def __getitem__(self, _: int) -> Page:
        return Page(self.text)


def test_owner_name_and_unique_cif(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "extract.pdf"
    source.write_bytes(b"synthetic")
    text = "Proprietari\n1) Fictional Works SRL, CIF:1234567\n2) Other Firm, CIF:7654321"
    monkeypatch.setattr(cf_owner.pdfium, "PdfDocument", lambda p: Document(p, text))
    located = cf_owner.read_owner_cui([source], "Fictional Works SRL")
    assert located.cui == "1234567"
    assert located.evidence.quote == "1) Fictional Works SRL, CIF:1234567"
    assert located.evidence.method == "anexa"
    with pytest.raises(EmaError) as error:
        cf_owner.read_owner_cui([source], "Unlisted Company")
    assert error.value.code == "cui_missing"


def test_conflicting_owner_cifs_require_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "extract.pdf"
    source.write_bytes(b"synthetic")
    text = "Proprietari\n1) Fictional Works SRL, CIF:1234567\n2) Fictional Works SRL, CIF:7654321"
    monkeypatch.setattr(cf_owner.pdfium, "PdfDocument", lambda p: Document(p, text))
    with pytest.raises(EmaError) as error:
        cf_owner.read_owner_cui([source], "Fictional Works SRL")
    assert error.value.code == "cui_conflict"
