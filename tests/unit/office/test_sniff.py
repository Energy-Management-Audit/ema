"""Content signatures override misleading client extensions."""

import struct
import zipfile

import pytest

from ema.core.office.sniff import FileKind, sniff


def _ole_stream(name):
    header = bytearray(512)
    header[:8] = bytes.fromhex("d0cf11e0a1b11ae1")
    struct.pack_into("<HHHH", header, 24, 0x3E, 3, 0xFFFE, 9)
    struct.pack_into("<H", header, 32, 6)
    struct.pack_into("<I", header, 44, 1)
    struct.pack_into("<I", header, 48, 1)
    struct.pack_into("<I", header, 56, 4096)
    struct.pack_into("<I", header, 60, 0xFFFFFFFE)
    struct.pack_into("<I", header, 68, 0xFFFFFFFE)
    struct.pack_into("<I", header, 76, 0)
    for offset in range(80, 512, 4):
        struct.pack_into("<I", header, offset, 0xFFFFFFFF)
    fat = bytearray(512)
    struct.pack_into("<II", fat, 0, 0xFFFFFFFD, 0xFFFFFFFE)
    for offset in range(8, 512, 4):
        struct.pack_into("<I", fat, offset, 0xFFFFFFFF)
    directory = bytearray(512)
    for index, (entry_name, entry_type) in enumerate((("Root Entry", 5), (name, 2))):
        offset = index * 128
        encoded = (entry_name + "\x00").encode("utf-16le")
        directory[offset : offset + len(encoded)] = encoded
        struct.pack_into("<H", directory, offset + 64, len(encoded))
        directory[offset + 66] = entry_type
        directory[offset + 67] = 1
        struct.pack_into("<III", directory, offset + 68, *([0xFFFFFFFF] * 3))
        struct.pack_into("<I", directory, offset + 116, 0xFFFFFFFE)
    struct.pack_into("<I", directory, 76, 1)
    return header + fat + directory


@pytest.mark.parametrize(
    ("name", "content", "kind", "mismatch"),
    [
        ("a.doc", _ole_stream("WordDocument"), FileKind.DOC, False),
        ("a.xls", _ole_stream("Workbook"), FileKind.XLS, False),
        ("a.xls", b"<!doctype html><html><body>table</body></html>", FileKind.HTML, True),
        ("a.pdf", b"%PDF-1.7\nbody\n%%EOF\n", FileKind.PDF, False),
        ("incomplete.pdf", b"%PDF-1.7\nbody", FileKind.UNKNOWN, True),
        ("a.jpg", b"\xff\xd8\xff\xe0", FileKind.IMAGE, False),
        ("a.bin", b"", FileKind.UNKNOWN, False),
        ("a.bin", b"\x00\x81\xff\x12", FileKind.UNKNOWN, False),
    ],
)
def test_signature(tmp_path, name, content, kind, mismatch):
    path = tmp_path / name
    path.write_bytes(content)
    detected = sniff(path)
    assert detected.kind == kind
    assert detected.mismatch is mismatch


@pytest.mark.parametrize(
    ("part", "kind"),
    [("word/document.xml", FileKind.DOCX), ("xl/workbook.xml", FileKind.XLSX)],
)
def test_office_zip_structure(tmp_path, part, kind):
    path = tmp_path / "misleading.zip"
    if kind == FileKind.DOCX:
        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        )
        root = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        )
    else:
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
        root = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            f'<Override PartName="/{part}" ContentType="{content_type}"/></Types>',
        )
        archive.writestr(part, root)
    detected = sniff(path)
    assert detected.kind == kind
    assert detected.mismatch


@pytest.mark.parametrize("parts", [("word/document.xml",), ("[Content_Types].xml",)])
def test_incomplete_office_zip_is_plain_zip(tmp_path, parts):
    path = tmp_path / "misleading.docx"
    with zipfile.ZipFile(path, "w") as archive:
        for part in parts:
            archive.writestr(part, "<part/>")
    detected = sniff(path)
    assert detected.kind == FileKind.ZIP
    assert detected.mismatch


@pytest.mark.parametrize(
    "content_types,main",
    [("garbage", "garbage"), ("<Types/>", "<document/>")],
)
def test_invalid_office_xml_is_plain_zip(tmp_path, content_types, main):
    path = tmp_path / "misleading.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", main)
    detected = sniff(path)
    assert detected.kind == FileKind.ZIP
    assert detected.mismatch
    assert "ZIP" in detected.detail


def test_pdf_eof_must_be_near_end(tmp_path):
    path = tmp_path / "truncated.pdf"
    path.write_bytes(b"%PDF-1.7\n%%EOF\n" + b"x" * 1100)
    detected = sniff(path)
    assert detected.kind == FileKind.UNKNOWN
    assert "EOF" in detected.detail
