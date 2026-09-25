"""Independent form-label and column checks for the S4 golden."""

from __future__ import annotations

from ema.energy_data.source import Located, normal

_FIELD_LABELS = {
    "year": ("anului anterior",),
    "name": ("denumirea operatorului economic", "denumirea unitatii"),
    "address": ("adresa postala",),
    "cui": ("cui",),
    "phone": ("telefon",),
    "fax": ("fax",),
    "website": ("pag internet", "pagina internet", "site web"),
    "website_target": ("pag internet", "pagina internet", "site web"),
    "caen_code": ("cod caen",),
    "caen_description": ("sector de activitate",),
    "contact_person": ("nume prenume", "nume si prenume persoana de contact", "nume"),
    "consumer_contact_person": ("nume prenume", "nume si prenume persoana de contact", "nume"),
    "ownership_state": ("stat",),
    "ownership_private": ("privat",),
    "total_tep": ("consum de energie total anual",),
    "electricity_grid_tep": ("consumul total anual din sen",),
    "electricity_grid_mwh": ("consumul total anual din sen",),
    "purchased_heat_tep": ("energie termica consumul total anual",),
    "purchased_heat_gcal": ("energie termica consumul total anual",),
    "electricity_pv_mwh": ("energie electrica produsa din surse recuperabile",),
    "natural_gas": ("gaze naturale",),
    "fuel_oil": ("pacura",),
    "clu": ("clu",),
    "petrol": ("benzina",),
    "diesel": ("motorina",),
    "coal": ("carbune",),
    "lpg": ("gpl",),
    "biomass": ("biomasa",),
    "electricity_grid": ("energie electrica consumul total anual",),
    "purchased_heat": (
        "energie termica consumul total anual",
        "energie termica consumul total annual din surse externe",
    ),
    "water_industrial": ("apa industriala",),
    "water_potable": ("apa potabila", "apa din reteaua publica"),
    "last_audit": ("data ultimului audit energetic efectuat",),
    "auditor": ("persoana fizica persoana juridica",),
    "boundary": ("contur bilant energetic",),
}
_ROW_FIELDS = {
    "year",
    "name",
    "address",
    "cui",
    "phone",
    "fax",
    "website",
    "website_target",
    "caen_code",
    "caen_description",
    "contact_person",
    "consumer_contact_person",
    "ownership_state",
    "ownership_private",
    "last_audit",
    "auditor",
    "boundary",
}
_RAW_UNITS = {
    "natural_gas": "mwh",
    "fuel_oil": "t",
    "clu": "t",
    "petrol": "t",
    "diesel": "t",
    "coal": "t",
    "lpg": "t",
    "biomass": "u m",
}
_MONTHS = (
    ("ianuarie", "ian"),
    ("februarie", "feb"),
    ("martie", "mar"),
    ("aprilie", "apr"),
    ("mai",),
    ("iunie", "iun"),
    ("iulie", "iul"),
    ("august", "aug"),
    ("septembrie", "sep"),
    ("octombrie", "oct"),
    ("noiembrie", "noi"),
    ("decembrie", "dec"),
)


def _cell(sheets: dict[str, list[list[str]]], item: Located, row: int, col: int) -> str:
    rows = sheets[item.ref.sheet]
    return (
        rows[row - 1][col - 1] if 1 <= row <= len(rows) and 1 <= col <= len(rows[row - 1]) else ""
    )


def _has_label(values: list[str], fragments: tuple[str, ...]) -> bool:
    return any(fragment in normal(value) for value in values for fragment in fragments)


def _field_location(sheets: dict[str, list[list[str]]], key: str, item: Located) -> None:
    row, col = item.ref.row, item.ref.col
    if key in _ROW_FIELDS:
        assert _has_label(sheets[item.ref.sheet][row - 1][: col - 1], _FIELD_LABELS[key]), (
            key,
            item.ref.a1,
        )
        return
    if key.endswith(("_raw", "_tep")) and key.rsplit("_", 1)[0] in _RAW_UNITS:
        carrier, suffix = key.rsplit("_", 1)
        assert _has_label(
            [_cell(sheets, item, row - offset, col) for offset in range(3, 7)],
            _FIELD_LABELS[carrier],
        ), (key, item.ref.a1)
        expected_unit = _RAW_UNITS[carrier] if suffix == "raw" else "tep"
        assert normal(_cell(sheets, item, row - 1, col)).startswith(expected_unit + " an"), (
            key,
            item.ref.a1,
        )
        return
    assert _has_label(
        [
            value
            for offset in (0, 1)
            for value in sheets[item.ref.sheet][row - offset - 1][: col - 1]
        ],
        _FIELD_LABELS[key],
    ), (key, item.ref.a1)
    expected_unit = "gcal" if key.endswith("_gcal") else "mwh" if key.endswith("_mwh") else "tep"
    assert expected_unit in normal(_cell(sheets, item, row, col - 1)), (key, item.ref.a1)


def _monthly_location(
    sheets: dict[str, list[list[str]]], carrier: str, month: int, item: Located
) -> None:
    row, col = item.ref.row, item.ref.col
    assert normal(_cell(sheets, item, row - 1, col)) in _MONTHS[month - 1], item.ref.a1
    assert _has_label(
        [value for offset in (2, 3) for value in sheets[item.ref.sheet][row - offset - 1][:3]],
        _FIELD_LABELS[carrier],
    ), (carrier, item.ref.a1)


def _measure_location(sheets: dict[str, list[list[str]]], item: Located, key: str) -> None:
    rows = sheets[item.ref.sheet]
    header = max(
        index
        for index, values in enumerate(rows, 1)
        if index < item.ref.row
        and any("descrierea masurii" in normal(value) for value in values[:8])
    )
    heading = normal(_cell(sheets, item, header, item.ref.col))
    unit = next(
        (
            normal(value)
            for row in (header + 1, header + 2)
            if (value := _cell(sheets, item, row, item.ref.col))
        ),
        "",
    )
    if key == "description":
        assert heading.startswith("descrierea masurii") or (
            not heading
            and normal(_cell(sheets, item, header, item.ref.col - 1)).startswith(
                "descrierea masurii"
            )
        ), item.ref.a1
    elif key == "location":
        assert item.ref.col <= next(
            col
            for col, value in enumerate(rows[header - 1], 1)
            if normal(value).startswith("descrierea masurii")
        ), item.ref.a1
    elif key == "commissioning_year":
        assert heading.startswith(("data punerii", "termenul de aplicare")), item.ref.a1
    elif key == "payback_years":
        matches = heading.startswith(("durata de recuperare", "estimarea duratei de recuperare"))
        assert matches, item.ref.a1
    elif key == "investment_thousand_lei":
        assert heading.startswith(("costul investitiei", "costul aplicarii masurii")), item.ref.a1
    elif key == "saving_mwh":
        assert unit.startswith("mwh an"), item.ref.a1
    elif key == "saving_tep":
        assert unit.startswith(("tep an", "t e p an")), item.ref.a1
    elif key == "saving_thousand_lei":
        assert heading.startswith("economia de cost"), item.ref.a1
    else:
        raise AssertionError(key)
