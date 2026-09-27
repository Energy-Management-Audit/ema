import subprocess
from pathlib import Path

import pytest

from ema.core import pdf


def test_bundled_tesseract_gets_tessdata_and_no_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, b"recognized", b"")

    monkeypatch.setattr(pdf.subprocess, "run", run)
    monkeypatch.setattr(pdf.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(pdf, "resource_path", tmp_path.joinpath)
    bundled = tmp_path / "tesseract" / "tesseract.exe"
    external = Path("/opt/homebrew/bin/tesseract")

    assert pdf._run_tesseract(bundled, b"image", "ron", 2, 6, "txt") == "recognized"
    assert calls[0][0][3:5] == ["--tessdata-dir", str(tmp_path / "tesseract" / "tessdata")]
    assert calls[0][1]["creationflags"] == 0x08000000
    assert pdf._run_tesseract(external, b"image", "ron", 2, 6, "txt") == "recognized"
    assert "--tessdata-dir" not in calls[1][0]
