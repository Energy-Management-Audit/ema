"""Client CLI registration and invoice journey."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ema.cli import _app
from ema.clients.registry import get_client
from ema.core.errors import EmaError
from ema.core.workspace import Workspace


@pytest.mark.parametrize(
    "command", [["invoices", "extract"], ["piee", "generate"], ["audit", "new"]]
)
def test_client_option_help_requires_registered_cui(command: list[str]) -> None:
    help_result = CliRunner().invoke(_app, [*command, "--help"])
    assert help_result.exit_code == 0, help_result.output
    assert "CUI-ul clientului înregistrat." in help_result.stdout


def test_clients_add_and_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EMA_WORKSPACE", str(tmp_path / "workspace"))
    runner = CliRunner()
    empty = runner.invoke(_app, ["clients", "list"])
    assert empty.exit_code == 0, empty.output
    assert json.loads(empty.stdout) == []

    added = runner.invoke(_app, ["clients", "add", "--name", "Synthetic", "--cui", "12345678"])
    assert added.exit_code == 0, added.output
    client = json.loads(added.stdout)
    assert client["id"]
    assert get_client(Workspace(tmp_path / "workspace"), client["id"]) == client

    without_cui = runner.invoke(_app, ["clients", "add", "--name", "Second synthetic"])
    assert without_cui.exit_code == 0, without_cui.output
    second = json.loads(without_cui.stdout)
    assert second["cui"] is None

    listed = runner.invoke(_app, ["clients", "list"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.stdout) == [second, client]


def test_clients_add_duplicate_cui_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EMA_WORKSPACE", str(tmp_path / "workspace"))
    runner = CliRunner()
    args = ["clients", "add", "--name", "Synthetic", "--cui", "12345678"]
    assert runner.invoke(_app, args).exit_code == 0
    duplicate = runner.invoke(_app, args)
    assert duplicate.exit_code != 0
    assert isinstance(duplicate.exception, EmaError)
    assert duplicate.exception.code == "client_exists"
    assert duplicate.exception.user_message_ro == "Clientul există deja."


def test_registered_client_can_extract_invoices(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EMA_WORKSPACE", str(tmp_path / "workspace"))
    invoices = tmp_path / "invoices"
    invoices.mkdir()
    (invoices / "synthetic.pdf").write_bytes(b"not a PDF")
    runner = CliRunner()
    added = runner.invoke(_app, ["clients", "add", "--name", "Synthetic", "--cui", "12345678"])
    assert added.exit_code == 0, added.output
    client = json.loads(added.stdout)
    assert client["cui"] == "12345678"
    extracted = runner.invoke(
        _app, ["invoices", "extract", str(invoices), "--client", client["cui"]]
    )
    assert extracted.exit_code == 0, extracted.output
    assert "synthetic.pdf: failed" in extracted.stdout
    assert "Lucrare: " in extracted.stdout
