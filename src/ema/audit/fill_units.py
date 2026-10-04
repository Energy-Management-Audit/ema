"""The 3.1.x unit headings: each process unit's title, verbatim from its own source (D3)."""

from __future__ import annotations

import re
from collections.abc import Mapping

from ema.audit.catalogue_types import PROCESS_UNIT
from ema.audit.fill_tools import FillDocument, FillTools
from ema.audit.process_units import ProcessUnits
from ema.core.errors import EmaError
from ema.core.logging import write_event
from ema.core.review.fields import fields

# A longer first line is a sentence of the scheme, not its title.
TITLE_CHARS = 200
_NAME = re.compile(rf"^{re.escape(PROCESS_UNIT)}(\d+)\.name$")


def _first_line(document: FillDocument) -> str | None:
    line = next((line.strip() for line in document.pages[0].splitlines() if line.strip()), None)
    return line if line is not None and len(line) <= TITLE_CHARS else None


def unit_titles(
    units: ProcessUnits, documents: Mapping[str, FillDocument]
) -> list[tuple[str, str] | None]:
    """Per unit, the dossier file and the line that names it: a scheme file's first line, or the
    Fişa block's `Flux` paragraph. None where the source has no such line, or is not read."""
    by_sha = {document.sha: name for name, document in documents.items()}
    if units.source == "fisa":
        name = by_sha.get(units.fisa_sha or "")
        return [
            (name, units.block(number)[0].strip()) if name is not None else None
            for number in range(1, units.count + 1)
        ]
    titles: list[tuple[str, str] | None] = []
    for files in units.schemes:
        lines = (
            (by_sha[sha], line)
            for _, sha in files
            if sha in by_sha and (line := _first_line(documents[by_sha[sha]])) is not None
        )
        titles.append(next(lines, None))
    return titles


def record_unit_names(
    tools: FillTools, units: ProcessUnits, documents: Mapping[str, FillDocument]
) -> int:
    """Record each unit's name, mark a unit without one missing, and drop names of units a
    previous dossier had. Returns how many names were recorded."""
    titles = unit_titles(units, documents)
    recorded = 0
    for number, title in enumerate(titles, 1):
        name, line = title or (None, "")
        try:
            tools.record_unit_name(number, name, line)
            recorded += name is not None
        except EmaError as exc:
            tools.record_unit_name(number, None)
            with tools.ws.connect() as db, tools.ws.job_log(db, tools.job) as handle:
                write_event(handle, "unit_name_failed", stage="fill", unit=number, code=exc.code)
    for item in fields(tools.ws, tools.job):
        match = _NAME.match(item.key)
        if match and int(match.group(1)) > len(titles) and item.presence == "found":
            tools.record_unit_name(int(match.group(1)), None)
    return recorded
