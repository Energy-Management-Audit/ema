"""A missing or mismatched cost is inferred from the consumption sheet and named in the review."""

from decimal import Decimal
from pathlib import Path

from ema.audit.data_flags import cost_flags, flags
from ema.audit.render_dataset import reviewed_costs
from ema.core.review.models import Field
from ema.energy_data.prices import read_prices

FIXTURE = read_prices(
    Path(__file__).parents[2] / "fixtures" / "prices" / "energy_prices_fixture.json"
)


def _field(key: str, value: float, unit: str, *, review: str = "pending") -> Field:
    return Field(
        id=key,
        job_id="synthetic",
        key=key,
        label=key,
        value_type="number",
        unit=unit,
        value=Decimal(str(value)),
        state="supplied",
        presence="found",
        review=review,  # type: ignore[arg-type]
        evidence=[f"evidence:{key}"],
        confidence="exact",
    )


def _fields(*items: Field) -> dict[str, Field]:
    return {item.key: item for item in items}


def test_declared_cost_off_by_more_than_25_percent_is_inferred() -> None:
    fields = _fields(
        _field("carrier.electricity_grid.2024", 1_068.47, "MWh"),
        _field("audit.economics.electricity_costs_lei.2024", 500_000, "lei"),
    )
    [issue] = cost_flags(fields, FIXTURE)
    assert issue.code == "data_cost_inferred"
    assert issue.message == (
        "Energie electrică din SEN 2024: cost declarat 500.000,00 lei, diferit de consumul din "
        "foaia de consumuri; se folosește costul estimat 868.025,03 lei "
        "(Eurostat nrg_pc_205, 2024)."
    )
    assert issue.field_id == "audit.economics.electricity_costs_lei.2024"
    assert issue.evidence_ids == (
        "evidence:audit.economics.electricity_costs_lei.2024",
        "evidence:carrier.electricity_grid.2024",
    )


def test_declared_cost_within_25_percent_raises_nothing() -> None:
    fields = _fields(
        _field("carrier.electricity_grid.2024", 1_000, "MWh"),
        _field("audit.economics.electricity_costs_lei.2024", 1_000 * 812.4 * 1.24, "lei"),
    )
    assert cost_flags(fields, FIXTURE) == []


def test_missing_cost_is_inferred_from_the_monthly_quantities() -> None:
    fields = _fields(
        *(_field(f"carrier.diesel.2024.{month:02d}", 1, "t") for month in range(1, 13)),
    )
    [issue] = cost_flags(fields, FIXTURE)
    assert issue.code == "data_cost_inferred"
    assert issue.message == (
        "Motorină 2024: cost nedeclarat; se folosește costul estimat 87.366,36 lei "
        "(Comisia Europeană, Weekly Oil Bulletin, 2024)."
    )


def test_rejected_cost_counts_as_missing() -> None:
    fields = _fields(
        _field("carrier.diesel.2024", 10, "t"),
        _field("audit.economics.diesel_costs_lei.2024", 72_805.3, "lei", review="rejected"),
    )
    [issue] = cost_flags(fields, FIXTURE)
    assert issue.message.startswith("Motorină 2024: cost nedeclarat;")


def test_unpriced_unit_gives_data_cost_unpriced() -> None:
    fields = _fields(
        _field("carrier.natural_gas.2024", 5_000, "Nm3"),
        _field("audit.economics.gas_costs_lei.2024", 10_000, "lei"),
    )
    [issue] = cost_flags(fields, FIXTURE)
    assert issue.code == "data_cost_unpriced"
    assert issue.message == (
        "Gaze naturale 2024: costul nu poate fi estimat "
        "(unitatea Nm3 nu are preț oficial în tabel)."
    )


def test_no_positive_quantity_or_partial_months_raise_nothing() -> None:
    fields = _fields(
        _field("carrier.lpg.2024", 0, "t"),
        _field("audit.economics.lpg_costs_lei.2024", 12_000, "lei"),
        *(_field(f"carrier.diesel.2024.{month:02d}", 1, "t") for month in range(1, 7)),
    )
    assert cost_flags(fields, FIXTURE) == []


def test_flags_include_the_cost_flags_from_the_bundled_table() -> None:
    fields = _fields(_field("carrier.diesel.2024", 10, "t"))
    assert [issue.code for issue in flags(fields)] == ["data_cost_inferred"]


def test_off_declaration_becomes_the_inferred_reviewed_cost() -> None:
    fields = _fields(
        _field("carrier.electricity_grid.2024", 1_068.47, "MWh"),
        _field("audit.economics.electricity_costs_lei.2024", 500_000, "lei"),
    )
    reviewed = reviewed_costs(fields, FIXTURE)["audit.economics.electricity_costs_lei.2024"]
    assert reviewed.value == Decimal("868025.03")
    assert reviewed.state == "calculated"
    assert reviewed.evidence == ["evidence:carrier.electricity_grid.2024"]
    assert reviewed.derivation is not None
    assert reviewed.derivation.inputs == ["carrier.electricity_grid.2024"]
    assert reviewed.derivation.factor_version == "Eurostat nrg_pc_205, 2024"
    [declared] = reviewed.alternatives
    assert declared.value == Decimal("500000")
    assert declared.evidence == ["evidence:audit.economics.electricity_costs_lei.2024"]
    # The warning still names the declaration and its evidence.
    [issue] = cost_flags(fields, FIXTURE)
    assert "cost declarat 500.000,00 lei" in issue.message
    assert "evidence:audit.economics.electricity_costs_lei.2024" in issue.evidence_ids


def test_missing_declaration_becomes_the_inferred_reviewed_cost() -> None:
    fields = _fields(_field("carrier.diesel.2024", 10, "t"))
    reviewed = reviewed_costs(fields, FIXTURE)["audit.economics.diesel_costs_lei.2024"]
    assert reviewed.value == Decimal("72805.30")
    assert reviewed.unit == "lei"
    assert reviewed.state == "calculated"
    assert reviewed.alternatives == []
    assert reviewed.evidence == ["evidence:carrier.diesel.2024"]


def test_kept_declaration_and_unpriced_quantity_are_not_rewritten() -> None:
    fields = _fields(
        _field("carrier.electricity_grid.2024", 1_000, "MWh"),
        _field("audit.economics.electricity_costs_lei.2024", 1_000 * 812.4 * 1.24, "lei"),
        _field("carrier.natural_gas.2024", 5_000, "Nm3"),
        _field("audit.economics.gas_costs_lei.2024", 10_000, "lei"),
    )
    assert reviewed_costs(fields, FIXTURE) == {}
