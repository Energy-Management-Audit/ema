"""CLI and core use cases must reach the same review state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_review import CATALOGUE, assert_error, evidence, get, setup
from typer.testing import CliRunner

from ema.cli import _app
from ema.core.errors import EmaError
from ema.core.review import decide, fields, log, propose, undo
from ema.core.review.models import Field
from ema.core.workspace import Workspace


def test_cli_and_use_cases_reach_same_review_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    direct = Workspace(tmp_path / "direct")
    via_cli = Workspace(tmp_path / "cli")
    direct_job, cli_job = setup(direct), setup(via_cli)
    runner = CliRunner()

    def command(
        job: str,
        field: Field,
        action: str,
        value: str | None = None,
        alternative: str | None = None,
    ) -> dict[str, object]:
        args = ["job", "decide", job, field.id, action]
        if value is not None:
            args.append(value)
        args += ["--on-revision", str(field.revision)]
        if alternative:
            args += ["--alternative", alternative]
        result = runner.invoke(_app, args)
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    direct_source = get(direct, direct_job, "source")
    d1 = decide(
        direct, direct_job, direct_source.id, "correct", direct_source.revision, "user", value=11
    )
    propose(direct, direct_job, CATALOGUE[0], 10, [evidence("again-direct")], state="extracted")
    d2 = decide(
        direct,
        direct_job,
        direct_source.id,
        "correct",
        get(direct, direct_job, "source").revision,
        "user",
        value=12,
    )
    assert_error("decision_superseded", lambda: undo(direct, direct_job, d1.id, "user"))
    undo(direct, direct_job, d2.id, "user")
    assert_error("field_changed", lambda: undo(direct, direct_job, d1.id, "user"))

    monkeypatch.setenv("EMA_WORKSPACE", str(via_cli.root))
    source = get(via_cli, cli_job, "source")
    c1 = command(cli_job, source, "correct", "11")
    propose(via_cli, cli_job, CATALOGUE[0], 10, [evidence("again-cli")], state="extracted")
    c2 = command(cli_job, get(via_cli, cli_job, "source"), "correct", "12")
    refused = runner.invoke(_app, ["job", "undo", cli_job, str(c1["id"])])
    assert isinstance(refused.exception, EmaError)
    assert refused.exception.code == "decision_superseded"
    result = runner.invoke(_app, ["job", "undo", cli_job, str(c2["id"])])
    assert result.exit_code == 0, result.output
    changed = runner.invoke(_app, ["job", "undo", cli_job, str(c1["id"])])
    assert isinstance(changed.exception, EmaError)
    assert changed.exception.code == "field_changed"

    for ws, job in ((direct, direct_job), (via_cli, cli_job)):
        conflict = get(ws, job, "conflict")
        if ws is direct:
            decide(
                ws,
                job,
                conflict.id,
                "choose",
                conflict.revision,
                "user",
                alternative=conflict.alternatives[0].id,
            )
            missing = get(ws, job, "missing")
            decide(ws, job, missing.id, "correct", missing.revision, "user", value=30)
        else:
            command(job, conflict, "choose", alternative=conflict.alternatives[0].id)
            command(job, get(ws, job, "missing"), "correct", "30")

    def field_state(ws: Workspace, job: str) -> list[tuple[object, ...]]:
        return [
            (
                field.key,
                str(field.value),
                field.state,
                field.presence,
                field.review,
                field.confidence,
                field.revision,
                sorted(str(item.value) for item in field.alternatives),
            )
            for field in fields(ws, job)
        ]

    def journal_state(ws: Workspace, job: str) -> list[tuple[object, ...]]:
        keys = {field.id: field.key for field in fields(ws, job)}
        return [
            (
                entry.action,
                keys[entry.field_id],
                entry.on_revision,
                str(entry.before.value),
                str(entry.after.value),
                bool(entry.undone_by),
            )
            for entry in log(ws, job)
        ]

    assert field_state(direct, direct_job) == field_state(via_cli, cli_job)
    assert journal_state(direct, direct_job) == journal_state(via_cli, cli_job)
