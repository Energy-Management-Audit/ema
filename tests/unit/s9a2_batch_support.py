"""Build a synthetic extraction artifact and exercise the shared batch review use case."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ema.core.jobs import StageOutcome, create_job, run_stage, subscribe
from ema.core.workspace import Workspace
from ema.invoices.artifact import encode
from ema.invoices.identity_review import confirm_client, readiness, resolved_outcomes
from ema.invoices.models import InputDocument
from ema.invoices.outcomes import DocumentOutcome, DocumentOutcomeStatus, ExtractionMetadata
from ema.invoices.parsers.protocol import SupplierParser


def assert_parser_batch_exportable(
    tmp_path: Path,
    parser: SupplierParser,
    document: InputDocument,
    *,
    companion_documents: tuple[InputDocument, ...] = (),
) -> None:
    documents = (document, *companion_documents)
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "synthetic", None)
    outcomes = []
    for index, item in enumerate(documents, start=1):
        drafts = tuple(parser.parse(item))
        assert drafts
        source = tmp_path / item.path.name
        source.write_bytes(b"synthetic PDF placeholder")
        digest = ws.add_file("synthetic", source)
        ws.set_slot(job, f"invoices/{index:04d}", digest, origin=source.name)
        metadata = ExtractionMetadata(
            parser_name=type(parser).__name__,
            layout_version=parser.layout_version,
            extraction_methods=("embedded",),
            ocr_pages=(),
            source_filename=source.name,
            document_type=parser.document_type,
            recognized_supplier=parser.supplier_name,
        )
        outcomes.append(
            DocumentOutcome(
                source_path=Path(source.name),
                status=DocumentOutcomeStatus.REQUIRES_REVIEW,
                drafts=drafts,
                metadata=metadata,
            )
        )

    def stage(ctx: Any) -> StageOutcome:
        ctx.read_slots("invoices")
        (ctx.artifact_dir() / "outcomes.json").write_text(encode(outcomes), encoding="utf-8")
        return StageOutcome()

    run_stage(ws, job, "invoices", stage)
    for _ in subscribe(ws, job):
        pass
    confirm_client(ws, job)
    assert readiness(ws, job).exportable == len(outcomes)
    assert all(row["status"] == "exportable" for row in resolved_outcomes(ws, job))
