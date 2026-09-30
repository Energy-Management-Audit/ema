"""Read the Anexa contact block from labels in both form generations."""

from __future__ import annotations

import re
from decimal import Decimal

from ema.core.office.sheets import Book, CellRef, CellValue, Sheet
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.source import Located, ReaderIssue, cell_at, filled, normal, right_of_label


def _label(sheet: Sheet, names: tuple[str, ...], issues: list[ReaderIssue]) -> CellRef | None:
    wanted = {normal(name) for name in names}
    matches: list[CellRef] = []
    for row in range(1, min(sheet.max_row, 40) + 1):
        for col in range(1, min(sheet.max_col, 8) + 1):
            value = cell_at(sheet, row, col, issues).value
            if isinstance(value, str) and normal(value) in wanted:
                matches.append(CellRef(sheet.name, row, col))
    if len(matches) > 1:
        issues.append(ReaderIssue("label_ambiguous", "/".join(names), matches[0]))
        return None
    return matches[0] if matches else None


def _following(sheet: Sheet, anchor: CellRef, issues: list[ReaderIssue]) -> Located | None:
    for col in range(anchor.col + 1, min(sheet.max_col, anchor.col + 3) + 1):
        value = filled(cell_at(sheet, anchor.row, col, issues))
        if value is not None:
            return value
    return None


def read_identity(book: Book, result: AnexaData) -> None:
    name = next(
        (n for n in book.sheet_names if normal(n) in {"date generale", "info companie"}),
        None,
    )
    if name is None:
        result.issues.append(ReaderIssue("sheet_missing", "Date generale / Info companie"))
        return
    sheet = book.sheet(name)
    _primary(sheet, result)
    _validate_name(book, result)
    _sites(result)
    _contact_fields(sheet, result)
    _ownership(sheet, result)
    _contact_person(sheet, result)


def _primary(sheet: Sheet, result: AnexaData) -> None:
    for key, labels in {
        "name": ("Denumirea operatorului economic", "Denumirea unităţii"),
        "address": ("Adresa poștală", "Adresa poştală"),
        "cui": ("CUI",),
    }.items():
        value = right_of_label(sheet, labels, result.issues)
        if value is not None:
            result.identity[key] = value


def _sites(result: AnexaData) -> None:
    declaration = result.identity.get("name")
    if declaration is None or not isinstance(declaration.value, str):
        return
    match = re.search(r"\bsucursalele\s+(.+?)\s+(?:și|şi|si)\s+(.+?)\s*$", declaration.value, re.I)
    if match is None:
        return
    operator = declaration.value[: match.start()].strip(" ,.;")
    if not operator:
        return
    result.identity["declared_name"] = declaration
    result.identity["name"] = Located(operator, declaration.ref)
    for index, site in enumerate(match.groups(), 1):
        result.identity[f"site_{index}_name"] = Located(site.strip(" ,.;").title(), declaration.ref)
    address = result.identity.get("address")
    if address is None or not isinstance(address.value, str):
        return
    matches = [
        index
        for index in (1, 2)
        if re.search(
            rf"(?:^| ){re.escape(normal(str(result.identity[f'site_{index}_name'].value)))}(?:$| )",
            normal(address.value),
        )
    ]
    if len(matches) == 1:
        result.identity[f"site_{matches[0]}_address"] = address


def _validate_name(book: Book, result: AnexaData) -> None:
    name = result.identity.get("name")
    address = result.identity.get("address")
    if name is None or address is None:
        return
    normalized_name = normal(str(name.value))
    normalized_address = normal(str(address.value))
    if not normalized_address or normalized_address not in normalized_name:
        return
    result.issues.append(ReaderIssue("name_is_address", str(name.value), name.ref))
    del result.identity["name"]
    for sheet_name in book.sheet_names:
        sheet = book.sheet(sheet_name)
        alternative = right_of_label(
            sheet, ("Denumirea operatorului economic", "Denumirea unităţii", "Denumire"), []
        )
        if alternative is not None and normal(str(alternative.value)) != normalized_name:
            result.identity["name"] = alternative
            result.name_origin = alternative.ref.a1
            return


def _contact_fields(sheet: Sheet, result: AnexaData) -> None:
    for key, labels in {
        "phone": ("Telefon",),
        "fax": ("Fax",),
        "website": ("Pag. Internet", "Pagina Internet", "Site web"),
        "caen_code": ("Cod CAEN",),
        "caen_description": ("Sector de activitate",),
        "registrul_comertului": ("Registrul Comerțului", "Nr. Registrul Comerțului"),
    }.items():
        anchor = _label(sheet, labels, result.issues)
        if anchor is None:
            continue
        value = _following(sheet, anchor, result.issues)
        if value is not None:
            result.identity[key] = value
            if key == "website":
                cell = cell_at(sheet, value.ref.row, value.ref.col, result.issues)
                if cell.hyperlink:
                    result.identity["website_target"] = Located(cell.hyperlink, value.ref)
                else:
                    result.issues.append(ReaderIssue("hyperlink_missing", "website", value.ref))


def _ownership(sheet: Sheet, result: AnexaData) -> None:
    # The form calls these ownership percentages, not monetary capital.
    for key, label in (("ownership_state", "Stat"), ("ownership_private", "Privat")):
        anchor = _label(sheet, (label,), result.issues)
        if anchor is None:
            continue
        candidate = None
        for col in range(anchor.col + 1, min(sheet.max_col, anchor.col + 3) + 1):
            cell = cell_at(sheet, anchor.row, col, result.issues)
            if cell.value is None or (isinstance(cell.value, str) and not cell.value.strip()):
                continue
            candidate = cell
            break
        if candidate is None:
            result.issues.append(ReaderIssue("ownership_flag", key, anchor))
            continue
        percent = _percentage(candidate)
        if percent is None:
            result.issues.append(ReaderIssue("ownership_flag", key, candidate.ref))
        else:
            result.identity[key] = Located(percent, candidate.ref, "%")


def _percentage(cell: CellValue) -> str | None:
    raw = cell.value
    percent = None
    if isinstance(raw, str):
        match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*%\s*", raw)
        if match:
            percent = Decimal(match.group(1).replace(",", "."))
    elif isinstance(raw, int | float) and not isinstance(raw, bool):
        number_format = re.sub(r'"[^"]*"|\\.|\[[^]]*\]', "", cell.number_format or "")
        if "%" in number_format:
            percent = Decimal(str(raw)) * 100
    if percent is None or not percent.is_finite() or not 0 <= percent <= 100:
        return None
    return str(percent).replace(".", ",") + "%"


def _contact_person(sheet: Sheet, result: AnexaData) -> None:
    contact = _label(
        sheet,
        ("Persoana de contact", "Persoana de contact din partea companiei"),
        result.issues,
    )
    consumer_contact = contact is not None
    if contact is None:
        contact = _label(
            sheet,
            (
                "Manager energetic sau Persoana de contact",
                "Manager energetic sau persoana de contact",
            ),
            result.issues,
        )
    if contact is not None:
        for row in range(contact.row + 1, min(contact.row + 4, sheet.max_row) + 1):
            heading = cell_at(sheet, row, contact.col, result.issues).value
            if isinstance(heading, str) and normal(heading) in {
                "nume prenume",
                "nume",
                "nume si prenume persoana de contact",
            }:
                value = _following(sheet, CellRef(sheet.name, row, contact.col), result.issues)
                if value is not None:
                    result.identity["contact_person"] = value
                    if consumer_contact:
                        result.identity["consumer_contact_person"] = value
                break
