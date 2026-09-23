"""Identify client files by content before any reader or converter sees them."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import olefile
from lxml import etree


class FileKind(StrEnum):
    XLSX = "xlsx"
    XLS = "xls"
    DOCX = "docx"
    DOC = "doc"
    PDF = "pdf"
    HTML = "html"
    IMAGE = "image"
    ZIP = "zip"
    TEXT = "text"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Sniffed:
    kind: FileKind
    mismatch: bool
    detail: str


_EXTENSIONS = {
    ".xlsx": FileKind.XLSX,
    ".xls": FileKind.XLS,
    ".docx": FileKind.DOCX,
    ".doc": FileKind.DOC,
    ".pdf": FileKind.PDF,
    ".html": FileKind.HTML,
    ".htm": FileKind.HTML,
    ".jpeg": FileKind.IMAGE,
    ".jpg": FileKind.IMAGE,
    ".png": FileKind.IMAGE,
    ".gif": FileKind.IMAGE,
    ".tif": FileKind.IMAGE,
    ".tiff": FileKind.IMAGE,
    ".bmp": FileKind.IMAGE,
    ".zip": FileKind.ZIP,
    ".txt": FileKind.TEXT,
}


def _ole_kind(path: Path) -> FileKind:
    try:
        with olefile.OleFileIO(str(path)) as ole:
            streams = {"/".join(parts).casefold() for parts in ole.listdir()}
    except (OSError, ValueError, TypeError):
        return FileKind.UNKNOWN
    if "worddocument" in streams:
        return FileKind.DOC
    if "workbook" in streams or "book" in streams:
        return FileKind.XLS
    return FileKind.UNKNOWN


def _zip_kind(path: Path) -> FileKind:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" in names:
                try:
                    types = etree.fromstring(archive.read("[Content_Types].xml"))
                    overrides = {
                        item.get("PartName", ""): item.get("ContentType", "")
                        for item in types
                        if etree.QName(item).localname == "Override"
                    }
                    checks = (
                        (
                            "word/document.xml",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
                            "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
                            "document",
                            FileKind.DOCX,
                        ),
                        (
                            "xl/workbook.xml",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
                            "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                            "workbook",
                            FileKind.XLSX,
                        ),
                    )
                    for part, content_type, namespace, root_name, kind in checks:
                        if part not in names or overrides.get(f"/{part}") != content_type:
                            continue
                        main = etree.fromstring(archive.read(part))
                        if (
                            etree.QName(main).localname == root_name
                            and etree.QName(main).namespace == namespace
                        ):
                            return kind
                except (etree.XMLSyntaxError, KeyError, ValueError):
                    pass
    except (OSError, zipfile.BadZipFile):
        return FileKind.UNKNOWN
    return FileKind.ZIP


def _text_kind(path: Path) -> FileKind:
    with path.open("rb") as stream:
        sample = stream.read(4096)
    if not sample:
        return FileKind.UNKNOWN
    encodings = ("utf-16",) if sample.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig",)
    for encoding in encodings:
        try:
            decoded = sample.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return FileKind.UNKNOWN
    if "\x00" in decoded or any(ord(char) < 32 and char not in "\t\r\n\f" for char in decoded):
        return FileKind.UNKNOWN
    if re.match(r"\s*(?:<!doctype\s+html\b|<html\b|<head\b|<body\b|<table\b)", decoded, re.I):
        return FileKind.HTML
    return FileKind.TEXT


def sniff(path: Path) -> Sniffed:
    """Return the content kind and whether a recognized extension disagrees."""
    with path.open("rb") as stream:
        header = stream.read(16)
    if header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        kind = _ole_kind(path)
    elif header.startswith(b"PK\x03\x04"):
        kind = _zip_kind(path)
    elif header.startswith(b"%PDF-"):
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 1024))
            trailer = stream.read()
        kind = FileKind.PDF if b"%%EOF" in trailer else FileKind.UNKNOWN
    elif header.startswith(
        (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM", b"II*\x00", b"MM\x00*")
    ):
        kind = FileKind.IMAGE
    else:
        kind = _text_kind(path)
    expected = _EXTENSIONS.get(path.suffix.casefold())
    mismatch = expected is not None and kind != expected
    if header.startswith(b"%PDF-") and kind == FileKind.UNKNOWN:
        detail = "PDF header without EOF marker near end"
    else:
        detail = f"{kind.value.upper()} saved as {path.suffix.lower()}" if mismatch else kind.value
    return Sniffed(kind, mismatch, detail)
