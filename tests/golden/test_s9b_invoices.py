"""S9b batch confirmation and source-pinned OCR regression."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests.invoice_helpers import undo_client

from ema.core.config import Settings
from ema.core.errors import EmaError
from ema.invoices import confirm_client, export, readiness
from ema.invoices.identity_review import batch_client

from .s9b_exceptions import ALIVE_PINS, ENGIE_PINS
from .test_s9a_invoices import _SOURCE_FIELDS, _baseline, _run_case

_ALIVE_POSITIONS = {
    "01.2024 Adv.pdf": 8,
    "01.2024 Final.pdf": 16,
    "02.2024 Adv.pdf": 8,
    "02.2024 Final.pdf": 16,
    "03.2024 Adv.pdf": 8,
    "03.2024 Final.pdf": 16,
    "04.2024.pdf": 10,
    "05.2024.pdf": 8,
    "06.2024.pdf": 8,
    "07.2024.pdf": 8,
    "08.2024.pdf": 9,
    "09.2024.pdf": 8,
    "10.2024.pdf": 8,
}


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()[:20]


def _field_differences(
    name: str, draft: dict, prior: dict
) -> dict[tuple[str, str], tuple[int, object]]:
    differences: dict[tuple[str, str], tuple[int, object]] = {}
    for key, old in prior["fields"].items():
        if key in {"client_name", "client_tax_id"}:
            continue  # S9b reads the printed buyer column that legacy OCR missed.
        current = draft["fields"].get(key)
        if current is None or (current["value"], current["status"]) != (
            old["value"],
            old["status"],
        ):
            assert current is not None
            page = current["evidence"][0]["page_number"] if current["evidence"] else 0
            differences[(name, key)] = (page, (current["value"], current["status"]))
    return differences


def _price_differences(
    name: str, draft: dict, prior: dict
) -> dict[tuple[str, str], tuple[int, object]]:
    differences: dict[tuple[str, str], tuple[int, object]] = {}
    prices = draft["price_details"]
    previous = prior["price_details"]
    if len(prices) != len(previous):
        differences[(name, "price_count")] = (0, len(prices))
    for index, (detail, old) in enumerate(zip(prices, previous, strict=False)):
        if any(detail[key] != old[key] for key in _SOURCE_FIELDS):
            differences[(name, f"price{index}")] = (
                detail["evidence"]["page_number"],
                {key: detail[key] for key in _SOURCE_FIELDS},
            )
    return differences


def _raw_regression(
    raw: list[dict], baseline: list[dict], pin_set: str, expected_count: int
) -> set[str]:
    originals = {str(row["source_path"]): row for row in baseline}
    assert len(raw) == len(baseline)
    observed: dict[tuple[str, str], tuple[int, object]] = {}
    names: set[str] = set()
    parsed_count = 0
    for row in raw:
        original = originals[str(row["source_path"])]
        if row["status"] == "incompatible":
            assert original["status"] == "incompatible"
            continue
        parsed_count += 1
        for draft, prior in zip(row["drafts"], original["drafts"], strict=True):
            assert draft["supplier"] == prior["supplier"]
            observed.update(_field_differences(row["source_path"], draft, prior))
            observed.update(_price_differences(row["source_path"], draft, prior))
            name = draft["fields"]["client_name"]["value"]
            if name:
                names.add(str(name))
    assert parsed_count == expected_count
    pins = ALIVE_PINS if pin_set == "ALIVE CAPITAL S.A." else ENGIE_PINS
    expected = set(pins)
    assert set(observed) == expected, f"raw parser regression: {set(observed) ^ expected}"
    for key, (page, value) in observed.items():
        pin = pins[key]
        if page:
            assert page == pin.page, key
        assert _digest(value) == pin.digest, key
    return names


def _alive_positions(raw: list[dict]) -> None:
    checked: set[str] = set()
    for row in raw:
        for draft in row["drafts"]:
            if draft["supplier"] != "ALIVE CAPITAL S.A.":
                continue
            name = row["source_path"]
            checked.add(name)
            expected = _ALIVE_POSITIONS[name]
            assert draft["metadata"]["parsed_position_count"] == expected, name
            printed = draft["metadata"]["printed_position_count"]
            if name.startswith(("01.", "02.", "03.", "04.", "05.")):
                assert printed == expected, name
            else:
                assert printed is None, name
    assert checked == set(_ALIVE_POSITIONS)


@pytest.mark.golden
@pytest.mark.parametrize(
    ("case", "pin_set", "expected_count"),
    [
        ("CLIENT-I2", "OMV PETROM S.A.", 24),
        ("invoice-case-f", "ALIVE CAPITAL S.A.", 13),
    ],
)
def test_s9b_batch_confirmation_and_parser_regression(
    tmp_path: Path, case: str, pin_set: str, expected_count: int
) -> None:
    if pin_set == "ALIVE CAPITAL S.A.":
        assert Settings().tesseract_path.is_file(), "ALIVE golden requires configured Tesseract"
    baseline, _ = _baseline(case)
    ws, job, raw = _run_case(tmp_path, case, baseline)
    names = _raw_regression(raw, baseline, pin_set, expected_count)
    if pin_set == "ALIVE CAPITAL S.A.":
        _alive_positions(raw)
    field, proposal = batch_client(ws, job)
    assert proposal is not None and field.review == "pending"
    assert proposal.name in names or any(
        proposal.name in candidate["names"] for candidate in proposal.candidates
    )
    with ws.connect() as db:
        destination = ws.job_path(db, job) / "outputs" / "Facturi.xlsx"
    with pytest.raises(EmaError) as blocked:
        export(ws, job, destination)
    assert blocked.value.code == "invoices_unconfirmed_client"
    if pin_set == "ALIVE CAPITAL S.A.":
        assert proposal.tax_id is not None
        assert len(proposal.pod_fill) == 1
        assert len(proposal.pod_fill[0]["files"]) == 8
        assert len({item["file"] for item in proposal.pod_fill[0]["sources"]}) == 5
    decision = confirm_client(ws, job)
    assert readiness(ws, job).exportable == expected_count
    assert export(ws, job, destination).is_file()
    if case == "CLIENT-I2":
        supplier_files = {
            supplier: {
                row["source_path"]
                for row in raw
                if any(draft["supplier"] == supplier for draft in row["drafts"])
            }
            for supplier in ("OMV PETROM S.A.", "ENGIE Romania S.A.")
        }
        assert len(supplier_files["OMV PETROM S.A."]) == 13
        assert len(supplier_files["ENGIE Romania S.A."]) == 11
        second = tmp_path / "second"
        _, second_job, _ = _run_case(second, case, baseline, ws)
        _, remembered = batch_client(ws, second_job)
        assert remembered is not None and remembered.memory
    undo_client(ws, job, decision.id)
    assert not readiness(ws, job).final_ok
    assert readiness(ws, job).exportable == 0
    with pytest.raises(EmaError) as undone:
        export(ws, job, destination)
    assert undone.value.code == "invoices_unconfirmed_client"
    if case == "CLIENT-I2":
        forgotten = tmp_path / "after-undo"
        _, forgotten_job, _ = _run_case(forgotten, case, baseline, ws)
        _, forgotten_proposal = batch_client(ws, forgotten_job)
        assert forgotten_proposal is not None and not forgotten_proposal.memory
