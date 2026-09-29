"""Windows Word COM identity and real conversion acceptance."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psutil
import pytest

from ema.core.config import Settings
from ema.core.office.errors import OfficeError
from ema.core.office.word_api import word_available, worker_command
from ema.core.office.word_child import WordChild

pytestmark = [pytest.mark.golden, pytest.mark.word]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Word COM only")
def test_timeout_preserves_bystander_and_normal_conversion(
    reference_library: Path, tmp_path: Path
) -> None:
    settings = Settings()
    if not word_available(settings):
        pytest.skip("Word is not configured")
    received = reference_library / "audit/cases/audit-case-a/received"
    source = next(path for path in received.iterdir() if path.suffix.lower() == ".doc")
    bystander = subprocess.Popen([str(settings.word_path), "/n"])
    identity = psutil.Process(bystander.pid).create_time()
    try:
        with pytest.raises(OfficeError) as error:
            WordChild(worker_command(), 0.5).convert_doc(source, tmp_path / "timeout.docx")
        assert error.value.code == "word_timeout"
        assert bystander.poll() is None
        assert psutil.Process(bystander.pid).create_time() == identity
        assert not [
            process.pid
            for process in psutil.process_iter()
            if process.name().casefold() == "winword.exe"
            and any(arg.casefold() == "/automation" for arg in process.cmdline())
        ]
        WordChild(worker_command(), settings.word_timeout_s).convert_doc(
            source, tmp_path / "converted.docx"
        )
        assert (tmp_path / "converted.docx").is_file()
    finally:
        bystander.terminate()
        bystander.wait(timeout=10)
