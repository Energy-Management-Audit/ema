"""Run the piee-case-a PIEE journey and compare Mac/Windows document contents."""

from __future__ import annotations

import argparse
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pypdfium2
from lxml import etree

from ema.core.jobs import status, subscribe
from ema.core.workspace import Workspace
from ema.piee.workflow import start_generate_for_job

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SKIP = {"docProps/core.xml", "docProps/app.xml"}
DRAFTS = {"PIEE-draft.docx", "Prelucrare-date.xlsx"}
WORD_SAVED = {"PIEE-final.docx", "Audit-ciorna.docx", "Audit-final.docx"}


def _parts(raw: bytes) -> dict[str, bytes]:
    with ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist() if name not in SKIP}


def _package_equal(left: bytes, right: bytes, prefix: str = "") -> str | None:
    a, b = _parts(left), _parts(right)
    if a.keys() != b.keys():
        return f"{prefix}parts {sorted(a.keys() ^ b.keys())}"
    for name in sorted(a):
        part = f"{prefix}{name}"
        if a[name].startswith(b"PK\x03\x04") and b[name].startswith(b"PK\x03\x04"):
            difference = _package_equal(a[name], b[name], part + "/")
        elif name.endswith((".xml", ".rels")):
            difference = (
                None
                if etree.tostring(etree.fromstring(a[name]), method="c14n")
                == etree.tostring(etree.fromstring(b[name]), method="c14n")
                else part
            )
        else:
            difference = None if a[name] == b[name] else part
        if difference:
            return difference
    return None


def _word_content(raw: bytes) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    parts = _parts(raw)
    root = etree.fromstring(parts["word/document.xml"])
    paragraphs: list[str] = []
    toc: list[tuple[str, str]] = []
    for paragraph in root.iter(W + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(W + "t"))
        paragraphs.append(text)
        props = paragraph.find(W + "pPr")
        style = props.find(W + "pStyle") if props is not None else None
        texts = list(paragraph.iter(W + "t"))
        if (
            style is not None
            and (style.get(W + "val") or "").upper().startswith("TOC")
            and texts
            and (texts[-1].text or "").isdecimal()
        ):
            toc.append((text[: -len(texts[-1].text or "")], texts[-1].text or ""))
    names = sorted(name for name in parts if name.startswith("word/charts/") or "embedding" in name)
    return paragraphs, toc, names


def _saved_equal(left: bytes, right: bytes) -> str | None:
    a, b = _word_content(left), _word_content(right)
    for label, first, second in (
        ("TOC", a[1], b[1]),
        ("paragraph", a[0], b[0]),
        ("chart/embedding parts", a[2], b[2]),
    ):
        for index, (one, two) in enumerate(zip(first, second, strict=False), 1):
            if one != two:
                return f"{label} {index}: {one!r} != {two!r}"
        if len(first) != len(second):
            return f"{label} count {len(first)} != {len(second)}"
    return None


def _pdf_equal(left: bytes, right: bytes) -> str | None:
    first, second = pypdfium2.PdfDocument(left), pypdfium2.PdfDocument(right)
    if len(first) != len(second):
        return f"page count {len(first)} != {len(second)}"
    for index in range(len(first)):
        a = " ".join(first[index].get_textpage().get_text_range().split())
        b = " ".join(second[index].get_textpage().get_text_range().split())
        if a != b:
            return f"page {index + 1} text {a!r} != {b!r}"
    return None


def compare(left: Path, right: Path) -> bool:
    names = sorted(
        {path.name for root in (left, right) for path in root.iterdir() if path.is_file()}
    )
    if not names:
        print("DIFFERENT: no files")
        return False
    equal = True
    for name in names:
        a, b = left / name, right / name
        if not a.is_file() or not b.is_file():
            difference = "missing"
        elif name in DRAFTS:
            difference = _package_equal(a.read_bytes(), b.read_bytes())
        elif name in WORD_SAVED:
            difference = _saved_equal(a.read_bytes(), b.read_bytes())
        elif name.endswith(".pdf"):
            difference = _pdf_equal(a.read_bytes(), b.read_bytes())
        else:
            difference = None if a.read_bytes() == b.read_bytes() else "bytes"
        print(f"{name} | {'equal' if difference is None else 'DIFFERENT: ' + difference}")
        equal &= difference is None
    return equal


def _command(value: str) -> list[str]:
    return [value] if Path(value).is_file() else shlex.split(value)


def _json_lines(output: str) -> list[dict[str, object] | list[dict[str, object]]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith(("{", "["))]


def _run(command: list[str], env: dict[str, str], *, interactive: bool = False) -> str:
    if not interactive:
        completed = subprocess.run(command, env=env, check=False, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError(
                f"command failed ({completed.returncode}): {command}; stderr: "
                f"{completed.stderr.strip()}"
            )
        return completed.stdout
    if not sys.stdin.isatty():
        raise RuntimeError("final export requires an interactive terminal")
    with subprocess.Popen(
        command, env=env, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ) as process:
        assert process.stdout is not None
        chunks: list[str] = []
        while char := process.stdout.read(1):
            print(char, end="", flush=True)
            chunks.append(char)
        if process.wait() != 0:
            raise RuntimeError(f"command failed: {command}; output: {''.join(chunks)[-2000:]}")
    return "".join(chunks)


def _one(folder: Path, pattern: str) -> Path:
    matches = list(folder.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"expected one {pattern} in {folder.name}, found {len(matches)}")
    return matches[0]


def _resolve_conflicts(command: list[str], env: dict[str, str], job: str) -> None:
    for index in range(11):
        conflicts = _json_lines(
            _run([*command, "job", "fields", job, "--status", "conflict"], env)
        )[0]
        assert isinstance(conflicts, list)
        if not conflicts:
            return
        if index == 10:
            raise RuntimeError(
                "conflicts remain after 10 decisions: "
                + ", ".join(str(field["id"]) for field in conflicts)
            )
        field = conflicts[0]
        alternatives = field["alternatives"]
        if not alternatives:
            raise ValueError(f"conflict {field['id']} has no candidate")
        _run(
            [
                *command,
                "job",
                "decide",
                job,
                str(field["id"]),
                "choose",
                "--alternative",
                str(alternatives[0]["id"]),
                "--on-revision",
                str(field["revision"]),
            ],
            env,
        )


def run(ema: str, inputs: Path, out: Path) -> None:
    for key in ("EMA_PIEE_BASE_DOCUMENT", "EMA_PIEE_BASE_DIRECTORY"):
        if not os.environ.get(key):
            raise ValueError(f"{key} is required")
    if out.exists():
        raise FileExistsError(f"output already exists: {out}")
    out.mkdir(parents=True)
    env = {**os.environ, "EMA_WORKSPACE": str(out / "workspace")}
    command = _command(ema)
    _run([*command, "clients", "add", "--name", "Synthetic", "--cui", "12345678"], env)
    generated = _json_lines(
        _run(
            [
                *command,
                "piee",
                "generate",
                "--client",
                "12345678",
                "--year",
                "2025",
                "--anexa",
                str(_one(inputs, "Anexa*.xlsx")),
                "--necesar",
                str(_one(inputs, "Necesar*.xls")),
                "--prelucrare",
                str(_one(inputs, "*Prelucrare*.xls*")),
            ],
            env,
        )
    )[0]
    assert isinstance(generated, dict)
    job = str(generated["job"])
    _resolve_conflicts(command, env, job)
    ws = Workspace(out / "workspace")
    regeneration = start_generate_for_job(ws, job)
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == regeneration)
    if record["state"] != "ready":
        raise RuntimeError(f"PIEE regeneration failed: {record['error']}")
    with ws.connect() as db:
        rows = db.execute(
            "SELECT relative_path FROM outputs WHERE job_id=? AND run_id=?",
            (job, regeneration),
        ).fetchall()
    paths = {
        Path(str(row["relative_path"])).name.split("-", 1)[1]: ws.path(str(row["relative_path"]))
        for row in rows
    }
    output = _json_lines(
        _run(
            [*command, "job", "export", job, "--final", "--dest", str(out / "export")],
            env,
            interactive=True,
        )
    )
    rendered = next(
        Path(str(item["rendered_path"]))
        for item in output
        if isinstance(item, dict) and "rendered_path" in item
    )
    parity = out / "parity"
    parity.mkdir()
    for name in DRAFTS:
        shutil.copy2(paths[name], parity / name)
    shutil.copy2(rendered, parity / "PIEE-final.docx")
    shutil.copy2(rendered.with_suffix(".pdf"), parity / "PIEE-final.pdf")
    print(f"parity files: {', '.join(sorted(path.name for path in parity.iterdir()))}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    running = commands.add_parser("run")
    running.add_argument("--ema", required=True)
    running.add_argument("--inputs", type=Path, required=True)
    running.add_argument("--out", type=Path, required=True)
    comparing = commands.add_parser("compare")
    comparing.add_argument("mac", type=Path)
    comparing.add_argument("windows", type=Path)
    args = parser.parse_args()
    if args.action == "compare":
        return 0 if compare(args.mac, args.windows) else 1
    run(args.ema, args.inputs, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
