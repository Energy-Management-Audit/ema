"""One deterministic path through the bookmarked PIEE document engine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from docx.oxml.ns import qn

from ema.core.office.anchors import AnchorLedger, find, leftover_issues, strip
from ema.core.office.base_map import BaseMap
from ema.core.office.base_map import load as load_map
from ema.core.office.cell_text import set_paragraph_text
from ema.core.office.package import check_standalone, encoded, read_parts, write_parts, xml
from ema.energy_data.carriers import Carrier
from ema.piee.body_spans import render_body_spans
from ema.piee.body_text import remove_unsourced_recommendation, render_body_text
from ema.piee.charts import render_bar_charts
from ema.piee.dataset import PieeData
from ema.piee.extra_figures import render_extra_figures
from ema.piee.figure_numbering import renumber_figures, renumber_tables
from ema.piee.identity import identity_values
from ema.piee.identity_map import render_identity
from ema.piee.measure_tables import render_measure_tables
from ema.piee.monthly_figures import render_missing_monthly_figures
from ema.piee.number_spans import render_number_spans, render_year_spans
from ema.piee.pies import render_pies
from ema.piee.section_clones import render_section_clones
from ema.piee.signature import render_signature
from ema.piee.tables import render_tables
from ema.piee.toc import render_toc, render_toc_from_headings
from ema.piee.trends import render_trends
from ema.piee.water import render_missing_water, water_missing


@dataclass(frozen=True)
class DraftStatus:
    output: Path
    untouched: tuple[str, ...]
    package_issues: tuple[str, ...]
    leftover_parts: tuple[str, ...]

    @property
    def final_ready(self) -> bool:
        return not (self.untouched or self.package_issues or self.leftover_parts)


def _strip_bookmarks(source: Path, output: Path) -> None:
    parts = read_parts(source)
    for owner in tuple(parts):
        if not owner.endswith(".xml"):
            continue
        root = xml(parts, owner)
        if strip([root]):
            parts[owner] = encoded(root)
    write_parts(parts, output)


def _mark_unresolved(
    source: Path, output: Path, ledger: AnchorLedger, preserve: frozenset[str]
) -> None:
    """A draft must show a red gap instead of a stale base-client number or sentence."""
    parts = read_parts(source)
    roots = {
        owner: xml(parts, owner)
        for owner in parts
        if owner.startswith("word/") and owner.endswith(".xml")
    }
    for slot in sorted(ledger.untouched):
        if slot.startswith("section_") or slot in preserve:
            continue
        paragraph = find(roots.values(), slot)
        set_paragraph_text(paragraph, "n.d.", missing=True)
    parts.update({owner: encoded(root) for owner, root in roots.items()})
    write_parts(parts, output)


def _record_removed_figure_paragraphs(
    base: Path, current: Path, mapping: BaseMap, ledger: AnchorLedger
) -> None:
    original = read_parts(base)
    rendered = read_parts(current)
    present = {
        node.get(qn("w:name"))
        for owner in rendered
        if owner.startswith("word/") and owner.endswith(".xml")
        for node in xml(rendered, owner).iter(qn("w:bookmarkStart"))
    }
    for entry in mapping.elements:
        if entry.kind != "paragraph" or not (entry.slot or "").startswith("body_"):
            continue
        assert entry.slot is not None
        if f"_ema_{entry.slot}" in present:
            continue
        node = xml(original, entry.owner).find(entry.selector)
        if node is None or not any(descendant.tag.endswith("}chart") for descendant in node.iter()):
            raise ValueError(f"nonfigure paragraph disappeared: {entry.slot}")
        ledger.record(entry.slot, removed=True)


def load_approved_base(base_directory: Path) -> BaseMap:
    map_path = base_directory / "base-map.json"
    mapping = load_map(map_path)
    approval = json.loads((base_directory / "approval.json").read_text(encoding="utf-8"))
    map_sha = hashlib.sha256(map_path.read_bytes()).hexdigest()
    if approval.get("base_sha") != mapping.base_sha or approval.get("map_sha") != map_sha:
        raise ValueError("PIEE base map has not been approved for this version")
    return mapping


def compose_draft(
    data: PieeData, base_directory: Path, output: Path, generated_on: date
) -> DraftStatus:
    """Render a draft and report all remaining base slots before final export."""
    mapping = load_approved_base(base_directory)
    ledger = AnchorLedger(mapping.variable_slots)
    production = (
        str(data.necesar.production[0].name.value)
        if data.necesar.production
        else data.dataset.production_name.get("main")
    )
    values = identity_values(
        data.anexa, generated_on, production_name=production, analysis_year=data.year
    )
    with TemporaryDirectory() as directory:
        stages = [Path(directory) / f"stage-{index}.docx" for index in range(21)]
        render_identity(
            base_directory / "piee-master.docx",
            base_directory / "identity-spans.json",
            values,
            stages[0],
            ledger,
            mapping,
        )
        render_number_spans(
            stages[0], base_directory / "number-spans.json", data, stages[1], ledger
        )
        render_year_spans(stages[1], base_directory / "year-spans.json", data, stages[2], ledger)
        render_trends(stages[2], base_directory / "trend-spans.json", data, stages[3], ledger)
        render_body_spans(
            stages[3],
            base_directory / "body-spans.json",
            data,
            stages[4],
            ledger,
            water_missing=water_missing(data),
        )
        render_body_text(stages[4], data, stages[5], ledger)
        remove_unsourced_recommendation(
            stages[5], base_directory / "unsourced-slots.json", stages[6], ledger
        )
        render_tables(stages[6], data, stages[7], ledger)
        render_measure_tables(stages[7], data, stages[8], ledger)
        render_signature(stages[8], values, stages[9], ledger)
        render_bar_charts(stages[9], data, stages[10], ledger)
        render_pies(stages[10], data, stages[11], ledger)
        render_extra_figures(stages[11], data, stages[12])
        _record_removed_figure_paragraphs(
            base_directory / "piee-master.docx", stages[12], mapping, ledger
        )
        render_missing_monthly_figures(
            stages[12], base_directory / "figure-groups.json", data, stages[13], ledger
        )
        render_missing_water(
            stages[13], data, base_directory / "section-groups.json", stages[14], ledger
        )
        render_section_clones(
            stages[14], base_directory / "carrier-prototypes.json", data, stages[15], ledger
        )
        if any(
            carrier in data.dataset.carriers
            for carrier in (Carrier.electricity_cogen, Carrier.coke)
        ):
            render_toc_from_headings(stages[15], stages[16])
        else:
            render_toc(
                stages[15],
                base_directory / "toc-manifest.json",
                stages[16],
                water_missing=water_missing(data),
            )
        toc_slots = frozenset(
            json.loads((base_directory / "toc-manifest.json").read_text(encoding="utf-8"))[
                "number_slots"
            ]
        )
        if not water_missing(data):
            for slot in toc_slots:
                ledger.record(slot)
        _mark_unresolved(stages[16], stages[17], ledger, toc_slots)
        _strip_bookmarks(stages[17], stages[18])
        renumber_figures(stages[18], stages[19])
        renumber_tables(stages[19], stages[20])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(stages[20].read_bytes())
    denylist = tuple(
        json.loads((base_directory / "base-identity.json").read_text(encoding="utf-8"))
    )
    leftovers = tuple(leftover_issues(output, denylist))
    if leftovers:
        output.unlink(missing_ok=True)
        raise ValueError(f"base identity remains in {len(leftovers)} package parts")
    return DraftStatus(
        output,
        tuple(sorted(ledger.untouched)),
        tuple(check_standalone(output)),
        leftovers,
    )
