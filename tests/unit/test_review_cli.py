"""CLI review shares the core decisions and existing-final export path."""

import json
from pathlib import Path

import pytest
from tests.unit.test_review import FakeWorkflow, get, setup
from typer.testing import CliRunner

from ema.cli import _app
from ema.cli import review as cli_review
from ema.core.workspace import Workspace


def test_cli_review_and_noninteractive_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = setup(ws)
    monkeypatch.setenv("EMA_WORKSPACE", str(ws.root))
    monkeypatch.setattr(cli_review, "_workflow", lambda *_args: FakeWorkflow())
    runner = CliRunner()
    result = runner.invoke(_app, ["job", "checks", job])
    assert result.exit_code == 0, result.output
    assert not json.loads(result.stdout)["final_ok"]
    source = get(ws, job, "source")
    result = runner.invoke(
        _app,
        ["job", "decide", job, source.id, "correct", "11", "--on-revision", str(source.revision)],
    )
    assert result.exit_code == 0, result.output
    assert get(ws, job, "source").value == 11
    result = runner.invoke(_app, ["job", "log", job])
    assert result.exit_code == 0 and len(json.loads(result.stdout)) == 1
    result = runner.invoke(_app, ["job", "undo", job, json.loads(result.stdout)[0]["id"]])
    assert result.exit_code == 0, result.output
    assert get(ws, job, "source").value == 10
    result = runner.invoke(
        _app, ["job", "export", job, "--final", "--dest", str(tmp_path / "final.txt")]
    )
    assert result.exit_code == 1
    assert not (tmp_path / "final.txt").exists()
    conflict = get(ws, job, "conflict")
    result = runner.invoke(
        _app,
        [
            "job",
            "decide",
            job,
            conflict.id,
            "choose",
            "--on-revision",
            str(conflict.revision),
            "--alternative",
            conflict.alternatives[0].id,
        ],
    )
    assert result.exit_code == 0, result.output
    missing = get(ws, job, "missing")
    result = runner.invoke(
        _app,
        ["job", "decide", job, missing.id, "correct", "30", "--on-revision", str(missing.revision)],
    )
    assert result.exit_code == 0, result.output
    FakeWorkflow().render(ws, job, "final")
    monkeypatch.setattr(cli_review, "_terminal", lambda: True)
    command = ["job", "export", job, "--final", "--dest", str(tmp_path / "final.txt")]
    denied = runner.invoke(_app, command, input="n\n")
    assert denied.exit_code == 2 and not (tmp_path / "final.txt").exists()
    assert "rendered_path" in denied.stdout
    assert denied.stdout.index("rendered_path") < denied.stdout.index("Aprobaţi")
    assert denied.stdout.count("Aprobaţi") == 1
    accepted = runner.invoke(_app, command, input="y\n")
    assert accepted.exit_code == 0, accepted.output
    assert (tmp_path / "final.txt" / "final.txt").read_text(encoding="utf-8") == "final"
