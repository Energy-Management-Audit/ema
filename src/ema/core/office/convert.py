"""Convert a stored legacy Word version without replacing its original."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from ema.core.config import Settings
from ema.core.errors import EmaError
from ema.core.office.errors import OfficeError
from ema.core.office.sniff import FileKind, sniff
from ema.core.office.text_check import TextCheck, check_text
from ema.core.office.word import WordMac
from ema.core.workspace import SlotVersion, Workspace
from ema.core.workspace.conversion import publish_conversion

_MESSAGES = {
    "needs_conversion": "Fișierul DOC trebuie convertit în DOCX.",
    "convert_timeout": "Conversia fișierului DOC a depășit timpul permis.",
    "convert_failed": "Conversia fișierului DOC a eșuat.",
}


class ConversionFailed(EmaError):  # noqa: N818 - public contract names the failed conversion
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, _MESSAGES[code], detail)


@dataclass(frozen=True)
class Conversion:
    version: SlotVersion
    text_check: TextCheck


def stored_file(ws: Workspace, job: str, sha: str) -> tuple[str, Path]:
    """Resolve a job-owned immutable file through workspace metadata."""
    with ws.connect() as db:
        row = db.execute(
            "SELECT j.client_slug,f.relative_path FROM jobs j JOIN files f "
            "ON f.client_slug=j.client_slug AND f.sha=? "
            "WHERE j.id=? AND j.deleted=0",
            (sha, job),
        ).fetchone()
    if row is None:
        raise EmaError("file_missing", "Fişierul nu există.", sha)
    return str(row["client_slug"]), ws.path(str(row["relative_path"]))


def convert_doc(
    ws: Workspace, job: str, slot: str, version: SlotVersion, settings: Settings
) -> Conversion | None:
    if version.job_id != job or version.slot != slot or version not in ws.list_versions(job, slot):
        raise EmaError("version_missing", "Versiunea nu există.", f"{job}/{slot}/{version.version}")
    _, source = stored_file(ws, job, version.file_sha)
    if sniff(source).kind != FileKind.DOC:
        raise EmaError("file_type", "Fişierul nu este un document DOC.", source.name)
    if sys.platform != "darwin" or not settings.word_path.is_dir():
        raise ConversionFailed(
            "needs_conversion", "Open it in Word and save it as .docx, then add it again."
        )
    word = WordMac(app=settings.word_path, timeout_s=settings.word_timeout_s)
    with TemporaryDirectory(dir=ws.root) as temp:
        converted = Path(temp) / "converted.docx"
        try:
            word.convert_doc(source, converted)
            original = word.doc_text(source)
            check = check_text(original, converted)
        except OfficeError as exc:
            code = "convert_timeout" if exc.code == "word_timeout" else "convert_failed"
            raise ConversionFailed(code, f"{exc.code}: {exc.detail}") from exc
        except (OSError, ValueError, KeyError) as exc:
            raise ConversionFailed("convert_failed", f"{type(exc).__name__}: {exc}") from exc
        converted_version = publish_conversion(ws, job, slot, version, converted)
        if converted_version is None:
            return None
    return Conversion(converted_version, check)
