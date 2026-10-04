"""The 3.1.x unit headings: each process unit's name, proposed by extraction from its own source
and verified there (D3). A unit with no verified name is missing, so its heading keeps the marker.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from ema.audit.catalogue_types import process_unit_name, process_unit_number
from ema.audit.fill_files import file_ids
from ema.audit.fill_tools import FillDocument, FillTools
from ema.audit.process_units import ProcessUnits
from ema.core.review.fields import fields


def unit_name_sources(
    units: ProcessUnits | None, documents: Mapping[str, FillDocument]
) -> dict[str, str]:
    """Per unit name key, where the prompt lets its name be quoted from: the unit's scheme files,
    or the Fişa with the unit's `Flux` block. A unit whose source was not read is left out."""
    if units is None:
        return {}
    ids = {documents[name].sha: file_id for file_id, name in file_ids(documents).items()}
    if units.source == "fisa":
        fisa = ids.get(units.fisa_sha or "")
        return (
            {
                process_unit_name(number): f"{fisa}, blocul Flux {number}"
                for number in range(1, units.count + 1)
            }
            if fisa is not None
            else {}
        )
    sources: dict[str, str] = {}
    for number, files in enumerate(units.schemes, 1):
        read = sorted({ids[sha] for _, sha in files if sha in ids}, key=lambda item: int(item[1:]))
        if read:
            sources[process_unit_name(number)] = ", ".join(read)
    return sources


def drop_unit_names(tools: FillTools, asked: Collection[str]) -> None:
    """Mark missing each found name of a unit this run did not ask for: a unit above the count,
    or one whose source was not read."""
    for item in fields(tools.ws, tools.job):
        unit = process_unit_number(item.key)
        if unit is not None and item.key not in asked and item.presence == "found":
            tools.mark_missing({"key": item.key})
