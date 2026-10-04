"""Data suspicions stay in the review queue with evidence from both sources."""

import re
from datetime import UTC, datetime
from decimal import Decimal

from tests.workspace_jobs import create_job

from ema.audit.data_flags import QUARTER_FACTOR, flags
from ema.audit.sections import audit_readiness
from ema.core.review.fields import propose
from ema.core.review.models import Candidate, Cell, Evidence, Field, FieldSpec
from ema.core.workspace import Workspace


def _field(key: str, value: int, ref: str, *, candidates: list[Candidate] | None = None) -> Field:
    return Field(
        id=key,
        job_id="synthetic",
        key=key,
        label=key,
        value_type="number",
        unit="t",
        value=Decimal(value),
        state="supplied",
        presence="found",
        evidence=[ref],
        confidence="conflict" if candidates else "exact",
        alternatives=candidates or [],
    )


def test_gpl_cost_and_count_conflict() -> None:
    fields = {
        "carrier.lpg.2025": _field("carrier.lpg.2025", 0, "quantity"),
        "audit.economics.lpg_costs_lei.2025": _field(
            "audit.economics.lpg_costs_lei.2025", 100, "cost"
        ),
        "audit.vehicle.1.count": _field(
            "audit.vehicle.1.count",
            2,
            "document-a",
            candidates=[
                Candidate(id="a", value=2, evidence=["document-a"]),
                Candidate(id="b", value=3, evidence=["document-b"]),
            ],
        ),
    }
    found = {issue.code: issue for issue in flags(fields)}
    assert found["data_gpl_cost_no_quantity"].evidence_ids == ("quantity", "cost")
    assert found["data_count_conflict"].evidence_ids == ("document-a", "document-b")


def test_month_repeat_and_quarter_suspicion_require_two_sources() -> None:
    values = {1: 10, 2: 10, 3: 0, 4: 2, 5: 3, 6: 4}
    fields = {
        f"carrier.diesel.2025.{month:02d}": _field(
            f"carrier.diesel.2025.{month:02d}", value, f"month-{month}"
        )
        for month, value in values.items()
    }
    found = {issue.code: issue for issue in flags(fields)}
    assert found["data_month_repeat"].evidence_ids == ("month-1", "month-2")
    assert found["data_quarter_in_month"].evidence_ids[0] in {"month-1", "month-2"}
    assert QUARTER_FACTOR == 2.5
    del fields["carrier.diesel.2025.03"]
    assert "data_quarter_in_month" in {issue.code for issue in flags(fields)}
    fields["carrier.diesel.2025.03"] = _field("carrier.diesel.2025.03", 10, "month-3")
    assert "data_quarter_in_month" not in {issue.code for issue in flags(fields)}


def test_refused_change_is_nonblocking_warning() -> None:
    fields = {
        "carrier.diesel.2024": _field("carrier.diesel.2024", 0, "old"),
        "carrier.diesel.2025": _field("carrier.diesel.2025", 10, "new"),
    }
    found = [issue for issue in flags(fields) if issue.code == "data_change_refused"]
    assert len(found) == 1 and found[0].evidence_ids == ("old", "new")
    fields["carrier.diesel.2024"] = _field("carrier.diesel.2024", 10, "old")
    assert not any(issue.code == "data_change_refused" for issue in flags(fields))
    fields["carrier.diesel.2027"] = _field("carrier.diesel.2027", 10, "later")
    assert any(issue.code == "data_change_refused" for issue in flags(fields))


def test_flags_reach_audit_readiness_without_blocking(tmp_path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2025)
    for key, value, ref in (
        ("carrier.lpg.2025", 0, "A1"),
        ("audit.economics.lpg_costs_lei.2025", 100, "B1"),
    ):
        propose(
            ws,
            job,
            FieldSpec(key=key, label=key, value_type="number", unit="t"),
            Decimal(value),
            [
                Evidence(
                    id=ref,
                    provenance="document",
                    file_sha="a" * 64,
                    locator=Cell(sheet="Sheet", ref=ref),
                    method="questionnaire",
                    retrieved_at=datetime.now(UTC),
                    highlight="exact",
                )
            ],
            state="supplied",
        )
    readiness = audit_readiness(ws, job)
    assert any(issue.code == "data_gpl_cost_no_quantity" for issue in readiness.warnings)
    assert not any(issue.code == "data_gpl_cost_no_quantity" for issue in readiness.blocking)


def test_zero_summer_months_are_not_repeats() -> None:
    fields = {
        f"carrier.diesel.2025.{month:02d}": _field(
            f"carrier.diesel.2025.{month:02d}", 0, f"summer-{month}"
        )
        for month in (6, 7, 8)
    }
    assert not any(issue.code == "data_month_repeat" for issue in flags(fields))


def test_quarter_flag_cites_empty_month_of_same_quarter() -> None:
    values = {1: 100, 2: 0, 3: 0, 4: 12, 5: 10, 6: 11}
    fields = {
        f"carrier.diesel.2025.{month:02d}": _field(
            f"carrier.diesel.2025.{month:02d}", value, f"month-{month}"
        )
        for month, value in values.items()
    }
    found = next(issue for issue in flags(fields) if issue.code == "data_quarter_in_month")
    assert found.evidence_ids == ("month-1", "month-2")


def test_unit_mismatch_is_refused_with_warning() -> None:
    before = _field("carrier.diesel.2024", 10, "old")
    after = _field("carrier.diesel.2025", 15, "new").model_copy(update={"unit": "kg"})
    found = [
        issue
        for issue in flags({before.key: before, after.key: after})
        if issue.code == "data_change_refused"
    ]
    assert len(found) == 1
    assert "unități diferite" in found[0].message


def _diesel(values: dict[int, int]) -> dict[str, Field]:
    return {
        f"carrier.diesel.2025.{month:02d}": _field(
            f"carrier.diesel.2025.{month:02d}", value, f"month-{month}"
        )
        for month, value in values.items()
    }


def test_messages_name_the_carrier_and_month_in_romanian() -> None:
    repeat = flags(_diesel({1: 10, 2: 10, 3: 12}))
    quarter = flags(_diesel({1: 100, 2: 0, 3: 0, 4: 12, 5: 10, 6: 11}))
    refused = flags(
        {
            "carrier.diesel.2024": _field("carrier.diesel.2024", 0, "old"),
            "carrier.diesel.2025": _field("carrier.diesel.2025", 10, "new"),
        }
    )
    message = {issue.code: issue.message for issue in [*repeat, *quarter, *refused]}
    assert (
        message["data_month_repeat"]
        == "Luni consecutive egale: motorină 2025, ianuarie şi februarie."
    )
    assert (
        message["data_quarter_in_month"]
        == "Consum concentrat într-o lună: motorină 2025, luna ianuarie."
    )
    assert message["data_change_refused"] == "Schimbare omisă: motorină, 2024–2025: bază zero."


def test_no_internal_key_reaches_a_message() -> None:
    fields = {
        **_diesel({1: 100, 2: 100, 3: 0, 4: 12, 5: 10, 6: 11}),
        "carrier.diesel.2024": _field("carrier.diesel.2024", 0, "old"),
        "carrier.diesel.2025": _field("carrier.diesel.2025", 10, "new"),
        "carrier.lpg.2025": _field("carrier.lpg.2025", 0, "quantity"),
        "audit.economics.lpg_costs_lei.2025": _field(
            "audit.economics.lpg_costs_lei.2025", 100, "cost"
        ),
        "audit.vehicle.1.count": _field(
            "audit.vehicle.1.count",
            2,
            "document-a",
            candidates=[
                Candidate(id="a", value=2, evidence=["document-a"]),
                Candidate(id="b", value=3, evidence=["document-b"]),
            ],
        ).model_copy(update={"label": "Număr autovehicule"}),
    }
    found = flags(fields)
    assert {issue.code for issue in found} >= {
        "data_gpl_cost_no_quantity",
        "data_count_conflict",
        "data_month_repeat",
        "data_quarter_in_month",
        "data_change_refused",
    }
    assert not [issue.message for issue in found if re.search(r"\w\.\w", issue.message)]


def test_unknown_carrier_is_not_flagged() -> None:
    fields = {
        f"carrier.steam.2025.{month:02d}": _field(
            f"carrier.steam.2025.{month:02d}", value, f"steam-{month}"
        )
        for month, value in {1: 10, 2: 10, 3: 0, 4: 2}.items()
    }
    fields["carrier.steam.2024"] = _field("carrier.steam.2024", 0, "old")
    fields["carrier.steam.2026"] = _field("carrier.steam.2026", 10, "new")
    assert flags(fields) == []
