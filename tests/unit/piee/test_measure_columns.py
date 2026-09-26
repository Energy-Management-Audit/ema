"""B9 from the other build's cases: absent measure columns are fillable; savings key is singular."""

from __future__ import annotations

from pathlib import Path

from ema.core.jobs import create_job
from ema.core.office.sheets import CellRef
from ema.core.review import decide, fields
from ema.core.workspace import Workspace
from ema.energy_data.anexa_cells import AnexaData, Measure
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import EnergyDataset
from ema.energy_data.necesar_model import NecesarInfo
from ema.energy_data.source import Located
from ema.piee.annual_check import AnnualCheck
from ema.piee.dataset import PieeData
from ema.piee.intake import _record_measures  # pyright: ignore[reportPrivateUsage]
from ema.piee.views import list_measures


def test_a_measure_with_only_a_saving_gets_its_other_columns_as_fields(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "piee", "synthetic", 2026)
    cell = CellRef("Solutii EE planificate", 5, 2)
    row = Measure(
        "planned", Located("Replace motor", cell), None, {"saving_mwh": Located(12.5, cell)}
    )
    data = PieeData(
        2025,
        AnexaData(planned_measures=[row]),
        NecesarInfo(),
        None,
        EnergyDataset((2025,), {}),
        FACTORS_2026,
        (),
        AnnualCheck("missing", None, None),
    )
    _record_measures(ws, job, data, "synthetic-sha")
    by_key = {field.key: field for field in fields(ws, job)}
    for column in ("investment_thousand_lei", "commissioning_year", "payback_years"):
        assert by_key[f"measure.planned.1.{column}"].presence == "not_found"
    assert "measure.planned.1.savings_mwh" not in by_key
    assert by_key["measure.planned.1.saving_mwh"].presence == "found"
    term = by_key["measure.planned.1.commissioning_year"]
    assert term.value_type == "year"

    decide(ws, job, term.id, "correct", term.revision, "user", value="2027")

    assert {field.key: field for field in fields(ws, job)}[term.key].value == 2027
    [measure] = list_measures(ws, job)
    assert measure["savings_mwh"] == 12.5
    assert "measure.planned.1.investment_thousand_lei" in measure["missing"]
    assert "measure.planned.1.commissioning_year" not in measure["missing"]
