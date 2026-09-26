"""generate_draft: one shared use case for the CLI and MCP, with the document seams stubbed."""

import json
from pathlib import Path

import pytest
from tests.piee_seams import stub_piee_seams, synthetic_inputs
from typer.testing import CliRunner

from ema.cli import _app
from ema.core.errors import EmaError
from ema.core.workspace import Workspace
from ema.piee.workflow import GenerateRequest, generate_draft


def test_draft_is_the_document_and_workbook_the_spreadsheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_piee_seams(monkeypatch, tmp_path)
    anexa, necesar, prelucrare = synthetic_inputs(tmp_path / "in")
    ws = Workspace(tmp_path / "ws")

    result = generate_draft(ws, GenerateRequest("synthetic", 2025, anexa, necesar, prelucrare))

    assert result.draft.suffix == ".docx" and result.draft.is_file()
    assert result.workbook.suffix == ".xlsx" and result.workbook.is_file()
    assert result.draft.is_relative_to(ws.root) and result.workbook.is_relative_to(ws.root)


def test_draft_is_the_document_even_when_the_workbook_is_saved_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_piee_seams(monkeypatch, tmp_path)
    anexa, _, prelucrare = synthetic_inputs(tmp_path / "in")
    ws = Workspace(tmp_path / "ws")

    result = generate_draft(ws, GenerateRequest("synthetic", 2025, anexa, None, prelucrare))

    with ws.connect() as db:
        ordered = db.execute(
            "SELECT relative_path FROM outputs WHERE job_id=? AND run_id=? AND kind='draft' "
            "ORDER BY seq",
            (result.job, result.run),
        ).fetchall()
        old_pick = db.execute(
            "SELECT relative_path FROM outputs WHERE job_id=? AND run_id=? AND kind='draft'",
            (result.job, result.run),
        ).fetchone()
    assert [Path(str(row["relative_path"])).suffix for row in ordered] == [".xlsx", ".docx"]
    assert Path(str(old_pick["relative_path"])).suffix == ".xlsx"
    assert result.draft.suffix == ".docx" and result.workbook.suffix == ".xlsx"


def test_failing_stage_is_piee_generation_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_piee_seams(monkeypatch, tmp_path)

    def broken(*_args: object) -> None:
        raise EmaError("synthetic_failure", "Eșec sintetic.", "synthetic")

    monkeypatch.setattr("ema.piee.workflow.compose_draft", broken)
    anexa, _, _ = synthetic_inputs(tmp_path / "in")

    with pytest.raises(EmaError) as failed:
        generate_draft(Workspace(tmp_path / "ws"), GenerateRequest("synthetic", 2025, anexa))

    assert failed.value.code == "piee_generation_failed"


def test_cli_prints_job_run_draft_workbook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_piee_seams(monkeypatch, tmp_path)
    monkeypatch.setenv("EMA_WORKSPACE", str(tmp_path / "ws"))
    anexa, _, prelucrare = synthetic_inputs(tmp_path / "in")
    args = ["piee", "generate", "--client", "synthetic", "--year", "2025", "--anexa", str(anexa)]

    printed = CliRunner().invoke(_app, [*args, "--prelucrare", str(prelucrare)])

    assert printed.exit_code == 0, printed.output
    output = json.loads(printed.output)
    assert list(output) == ["job", "run", "draft", "workbook"]
    assert output["draft"].endswith(".docx") and Path(output["draft"]).is_absolute()
    assert output["workbook"].endswith(".xlsx")
