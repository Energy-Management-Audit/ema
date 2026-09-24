from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ema.core.errors import EmaError
from ema.invoices.models import (
    InvoiceDraft,
    IssueCode,
    IssueSeverity,
    ValidationIssue,
)


class DocumentOutcomeStatus(StrEnum):
    EXPORTABLE = "exportable"
    REQUIRES_REVIEW = "requires_review"
    DUPLICATE = "duplicate"
    UNSUPPORTED = "unsupported"
    INCOMPATIBLE = "incompatible"
    FAILED = "failed"


def reader_failure_code(error: EmaError) -> IssueCode:
    if error.code == "ocr_timeout":
        return IssueCode.OCR_TIMEOUT
    if error.code == "ocr_unavailable":
        return IssueCode.OCR_RUNTIME_UNAVAILABLE
    return IssueCode.PDF_READ_FAILED


@dataclass(frozen=True)
class ExtractionMetadata:
    parser_name: str | None
    layout_version: str | None
    extraction_methods: tuple[str, ...]
    ocr_pages: tuple[int, ...]
    source_filename: str
    document_type: str | None
    recognized_supplier: str | None
    technical_detail: str | None = None


@dataclass
class DocumentOutcome:
    source_path: Path
    status: DocumentOutcomeStatus
    drafts: tuple[InvoiceDraft, ...]
    metadata: ExtractionMetadata
    issues: tuple[ValidationIssue, ...] = ()
    reason: str | None = None

    @property
    def source_filename(self) -> str:
        return self.source_path.name

    @property
    def issue_codes(self) -> tuple[IssueCode, ...]:
        return tuple(
            issue.code
            for issue in (*self.issues, *(issue for draft in self.drafts for issue in draft.issues))
            if issue.code is not None
        )

    def refresh_status(self) -> None:
        if self.status in {
            DocumentOutcomeStatus.DUPLICATE,
            DocumentOutcomeStatus.UNSUPPORTED,
            DocumentOutcomeStatus.INCOMPATIBLE,
            DocumentOutcomeStatus.FAILED,
        }:
            return
        self.status = (
            DocumentOutcomeStatus.EXPORTABLE
            if self.drafts
            and all(draft.is_exportable for draft in self.drafts)
            and not any(issue.severity is IssueSeverity.ERROR for issue in self.issues)
            else DocumentOutcomeStatus.REQUIRES_REVIEW
        )


@dataclass
class BatchProcessingResult:
    outcomes: tuple[DocumentOutcome, ...]

    def refresh(self) -> None:
        for outcome in self.outcomes:
            outcome.refresh_status()

    @property
    def all_drafts(self) -> list[InvoiceDraft]:
        return [draft for outcome in self.outcomes for draft in outcome.drafts]

    @property
    def exportable(self) -> list[InvoiceDraft]:
        self.refresh()
        return [
            draft
            for outcome in self.outcomes
            if outcome.status is DocumentOutcomeStatus.EXPORTABLE
            for draft in outcome.drafts
        ]

    @property
    def requires_review(self) -> list[InvoiceDraft]:
        self.refresh()
        return [
            draft
            for outcome in self.outcomes
            if outcome.status is DocumentOutcomeStatus.REQUIRES_REVIEW
            for draft in outcome.drafts
        ]

    @property
    def excluded(self) -> list[DocumentOutcome]:
        return [
            outcome
            for outcome in self.outcomes
            if outcome.status
            in {
                DocumentOutcomeStatus.DUPLICATE,
                DocumentOutcomeStatus.UNSUPPORTED,
                DocumentOutcomeStatus.INCOMPATIBLE,
                DocumentOutcomeStatus.FAILED,
            }
        ]


def failed_document(path: Path, code: IssueCode, detail: str, message: str) -> DocumentOutcome:
    issue = ValidationIssue(None, IssueSeverity.ERROR, message, code)
    return DocumentOutcome(
        source_path=path,
        status=DocumentOutcomeStatus.FAILED,
        drafts=(),
        metadata=ExtractionMetadata(
            parser_name=None,
            layout_version=None,
            extraction_methods=(),
            ocr_pages=(),
            source_filename=path.name,
            document_type=None,
            recognized_supplier=None,
            technical_detail=detail or None,
        ),
        issues=(issue,),
        reason=message,
    )
