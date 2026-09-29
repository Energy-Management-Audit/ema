"""Calculated provenance stays in review while the draft prints only the number."""

import json

from tests.workspace_jobs import create_job

from ema.core.office.sheets import CellRef
from ema.core.review.fields import fields
from ema.core.workspace import Workspace
from ema.energy_data.anexa_cells import Measure
from ema.energy_data.source import Located
from ema.piee.measure_tables import _solution_row
from ema.piee.payback_review import record_payback_check


def test_missing_filed_payback_keeps_provenance_in_review_only(tmp_path) -> None:
    def value(content: str | float | int) -> Located:
        return Located(content, CellRef("Measures", 1, 1))

    row = Measure(
        "planned",
        value("Synthetic measure"),
        value(2027),
        {
            "investment_thousand_lei": value(12.0),
            "saving_thousand_lei": value(3.0),
        },
    )

    assert _solution_row(row)[2] == "4,00"

    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    record_payback_check(ws, job, "planned", 1, row, "a" * 64)
    field = next(item for item in fields(ws, job) if item.key == "measure.planned.1.payback_years")
    assert field.state == "calculated"
    assert field.label == "Calculat, necompletat în anexă"
    assert field.value == 4
    assert field.derivation is not None
    assert field.derivation.formula_id == "payback.cost_div_savings"
    assert field.derivation.inputs == [
        "measure.planned.1.investment_thousand_lei",
        "measure.planned.1.saving_thousand_lei",
    ]
    with ws.connect() as db:
        evidence = [
            json.loads(item["data"])
            for item in db.execute("SELECT data FROM evidence WHERE job_id=?", (job,))
        ]
    assert any(item["provenance"] == "calculated" for item in evidence)
