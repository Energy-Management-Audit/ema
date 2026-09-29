"""The privacy gates catch variants in text, paths, and compressed documents."""

import os
import subprocess
import zlib
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from scripts.check_outgoing_private_terms import outgoing_matches
from scripts.check_private_terms import load_guard, scan, scan_bytes


def test_private_terms_in_paths_and_content() -> None:
    matches = scan(
        "tests/client-name_case.py",
        "Client Nâme\nclient_name\nclient-name\nclient name\nclient_name_extra",
        ["client name"],
    )
    assert matches == [
        "tests/client-name_case.py:0: client name",
        "tests/client-name_case.py:1: client name",
        "tests/client-name_case.py:2: client name",
        "tests/client-name_case.py:3: client name",
        "tests/client-name_case.py:4: client name",
        "tests/client-name_case.py:5: client name",
    ]


def test_allow_list_only_covers_full_model_token() -> None:
    matches = scan(
        "example.py",
        "model-2.5-sample and sample client",
        ["sample"],
        [r"model-[a-z0-9._-]*-sample"],
    )
    assert matches == ["example.py:1: sample"]


def test_internal_separator_variants_match() -> None:
    assert scan("fixture.py", "A_B-C", ["ABC"]) == ["fixture.py:1: ABC"]


def test_common_romanian_adjective_is_preserved() -> None:
    assert scan("fixture.py", "tendință constantă", ["Constan" + "ța"]) == []


def test_local_guard_requires_mapping_but_ci_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMA_REFERENCE", raising=False)
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(FileNotFoundError, match=r"requires.*cases.toml"):
        load_guard()
    monkeypatch.setenv("CI", "true")
    assert load_guard() is None


def test_scans_office_members_and_deflated_pdf_streams() -> None:
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "<w:t>Client Nâme</w:t>")
    pdf = (
        b"<< /Filter /FlateDecode >>\nstream\n"
        + zlib.compress("Client Nâme".encode())
        + b"\nendstream"
    )
    assert scan_bytes("sample.docx", archive_bytes.getvalue(), ["client name"]) == [
        "sample.docx!word/document.xml:1: client name"
    ]
    assert scan_bytes("sample.xlsx", archive_bytes.getvalue(), ["client name"]) == [
        "sample.xlsx!word/document.xml:1: client name"
    ]
    assert scan_bytes("sample.pdf", pdf, ["client name"]) == ["sample.pdf!stream-1:1: client name"]


def test_outgoing_commits_include_messages_and_tracked_blobs(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)

    def git(*args: str) -> str:
        return subprocess.check_output(("git", *args), text=True).strip()

    monkeypatch.chdir(tmp_path)
    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.test")
    (tmp_path / "base.txt").write_text("safe", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "baseline")
    base = git("rev-parse", "HEAD")
    (tmp_path / "client-name.txt").write_text("Client Nâme", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "client_name update")
    matches = outgoing_matches(base, git("rev-parse", "HEAD"), ["client name"])
    assert any("commit-message:1: client name" in match for match in matches)
    assert any("client-name.txt:0: client name" in match for match in matches)
    assert any("client-name.txt:1: client name" in match for match in matches)
