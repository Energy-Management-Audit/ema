from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ema.core.errors import EmaError
from ema.invoices.configuration.field_catalog import (
    BILLING_PERIOD,
    INVOICE_NUMBER,
    LOCATION_IDENTIFIER,
)
from ema.invoices.configuration.user_messages import ISSUE_MESSAGES
from ema.invoices.models import (
    InputDocument,
    InvoiceDraft,
    IssueCode,
    IssueSeverity,
    ValidationIssue,
)
from ema.invoices.outcomes import (
    BatchProcessingResult,
    DocumentOutcome,
    DocumentOutcomeStatus,
    ExtractionMetadata,
    failed_document,
    reader_failure_code,
)
from ema.invoices.parsers.protocol import SupplierParser
from ema.invoices.reader import InvoiceDocumentReader

ProgressCallback = Callable[[int, int, Path], None]
OutcomeCallback = Callable[[DocumentOutcome], None]


class ProcessInvoiceFiles:
    def __init__(
        self,
        reader: InvoiceDocumentReader,
        extractor: ExtractInvoice,
    ) -> None:
        self._reader = reader
        self._extractor = extractor

    def execute(
        self,
        paths: Iterable[Path],
        *,
        progress: ProgressCallback | None = None,
        document_finished: OutcomeCallback | None = None,
        source_names: Sequence[str] | None = None,
    ) -> BatchProcessingResult:
        source_paths = tuple(paths)
        if source_names is not None and len(source_names) != len(source_paths):
            raise ValueError("Source names must align with input paths")
        outcomes: list[DocumentOutcome] = []
        seen_digests: dict[str, Path] = {}
        for index, path in enumerate(source_paths, start=1):
            source = Path(source_names[index - 1]) if source_names is not None else path
            if progress is not None:
                progress(index, len(source_paths), path)
            outcome = self._process_path(path, source, seen_digests)
            outcomes.append(outcome)
        self._deduplicate_identities(outcomes)
        if document_finished is not None:
            for outcome in outcomes:
                document_finished(outcome)
        return BatchProcessingResult(outcomes=tuple(outcomes))

    def _process_path(
        self, path: Path, source: Path, seen_digests: dict[str, Path]
    ) -> DocumentOutcome:
        digest = _file_digest(path)
        if digest is not None and digest in seen_digests:
            return self._duplicate_outcome(source, seen_digests[digest])
        if digest is not None:
            seen_digests[digest] = source
        try:
            document = replace(self._reader.read(path), path=source)
        except EmaError as error:
            return self.failure_outcome(
                source, reader_failure_code(error), f"{error.code}: {error.detail}"
            )
        except Exception as error:  # one bad file must not abort a batch
            return self.failure_outcome(source, IssueCode.PDF_READ_FAILED, str(error))
        try:
            return self._process_document(source, document)
        except Exception as error:  # isolate parser failures per file
            return self.failure_outcome(source, IssueCode.EXTRACTION_FAILED, str(error))

    def _deduplicate_identities(self, outcomes: list[DocumentOutcome]) -> None:
        seen: dict[tuple[object, ...], int] = {}
        for index, outcome in enumerate(outcomes):
            if (
                outcome.status
                not in {
                    DocumentOutcomeStatus.EXPORTABLE,
                    DocumentOutcomeStatus.REQUIRES_REVIEW,
                }
                or not outcome.drafts
            ):
                continue
            keys = tuple(_invoice_identity(draft) for draft in outcome.drafts)
            if any(key is None for key in keys):
                continue
            prior_indexes = {seen[key] for key in keys if key in seen}
            if not prior_indexes:
                for key in keys:
                    assert key is not None
                    seen[key] = index
                continue
            if len(prior_indexes) == 1:
                prior_index = next(iter(prior_indexes))
                prior = outcomes[prior_index]
                same_invoice = _compare_invoice_safely(outcome, prior, keys)
                if same_invoice is None:
                    continue
                if same_invoice:
                    outcomes[index] = self._duplicate_outcome(
                        outcome.source_path, prior.source_path
                    )
                    continue
            _record_identity_conflict(prior_indexes, index, keys, seen, outcomes)

    @staticmethod
    def _duplicate_outcome(path: Path, original_path: Path) -> DocumentOutcome:
        reason = f"{ISSUE_MESSAGES[IssueCode.DUPLICATE_DOCUMENT]} Original: {original_path.name}."
        issue = ValidationIssue(
            field_id=None,
            severity=IssueSeverity.WARNING,
            message=reason,
            code=IssueCode.DUPLICATE_DOCUMENT,
        )
        return DocumentOutcome(
            source_path=path,
            status=DocumentOutcomeStatus.DUPLICATE,
            drafts=(),
            metadata=ExtractionMetadata(
                parser_name=None,
                layout_version=None,
                extraction_methods=(),
                ocr_pages=(),
                source_filename=path.name,
                document_type=None,
                recognized_supplier=None,
            ),
            issues=(issue,),
            reason=reason,
        )

    def _process_document(self, path: Path, document: InputDocument) -> DocumentOutcome:
        extracted = self._extractor.execute_with_parser(document)
        parser = extracted.parser
        metadata = ExtractionMetadata(
            parser_name=type(parser).__name__ if parser is not None else None,
            layout_version=parser.layout_version if parser is not None else None,
            extraction_methods=tuple(
                dict.fromkeys(page.extraction_method for page in document.pages)
            ),
            ocr_pages=tuple(
                page.number for page in document.pages if page.extraction_method == "ocr"
            ),
            source_filename=path.name,
            document_type=parser.document_type if parser is not None else None,
            recognized_supplier=parser.supplier_name if parser is not None else None,
        )
        for draft in extracted.drafts:
            draft.metadata.update(
                {
                    "parser_name": metadata.parser_name,
                    "layout_version": metadata.layout_version,
                    "extraction_methods": metadata.extraction_methods,
                    "ocr_pages": metadata.ocr_pages,
                    "document_type": metadata.document_type,
                    "recognized_supplier": metadata.recognized_supplier,
                }
            )
        if parser is None:
            return DocumentOutcome(
                source_path=path,
                status=DocumentOutcomeStatus.REQUIRES_REVIEW,
                drafts=extracted.drafts,
                metadata=metadata,
                reason=ISSUE_MESSAGES[IssueCode.UNSUPPORTED_SUPPLIER],
            )
        if parser.document_type != "electricity_invoice":
            reason = next(
                (
                    issue.message
                    for draft in extracted.drafts
                    for issue in draft.issues
                    if issue.code is IssueCode.INCOMPATIBLE_DOCUMENT_TYPE
                ),
                ISSUE_MESSAGES[IssueCode.INCOMPATIBLE_DOCUMENT_TYPE],
            )
            return DocumentOutcome(
                source_path=path,
                status=DocumentOutcomeStatus.INCOMPATIBLE,
                drafts=extracted.drafts,
                metadata=metadata,
                reason=reason,
            )
        status = (
            DocumentOutcomeStatus.EXPORTABLE
            if extracted.drafts and all(draft.is_exportable for draft in extracted.drafts)
            else DocumentOutcomeStatus.REQUIRES_REVIEW
        )
        return DocumentOutcome(
            source_path=path,
            status=status,
            drafts=extracted.drafts,
            metadata=metadata,
        )

    @staticmethod
    def failure_outcome(
        path: Path,
        code: IssueCode,
        detail: str,
    ) -> DocumentOutcome:
        return failed_document(path, code, detail, ISSUE_MESSAGES[code])


def _compare_invoice_safely(
    current: DocumentOutcome,
    prior: DocumentOutcome,
    keys: tuple[tuple[object, ...] | None, ...],
) -> bool | None:
    try:
        return _same_invoice(current, prior, keys)
    except Exception as error:
        _mark_dedupe_error(current, error)
        _mark_dedupe_error(prior, error)
        return None


def _record_identity_conflict(
    prior_indexes: set[int],
    index: int,
    keys: tuple[tuple[object, ...] | None, ...],
    seen: dict[tuple[object, ...], int],
    outcomes: list[DocumentOutcome],
) -> None:
    for prior_index in prior_indexes | {index}:
        _mark_conflict(outcomes[prior_index])
    for key in keys:
        assert key is not None
        seen.setdefault(key, index)


def _file_digest(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _invoice_identity(draft: InvoiceDraft) -> tuple[object, ...] | None:
    values = [
        draft.fields.get(key) for key in (INVOICE_NUMBER, LOCATION_IDENTIFIER, BILLING_PERIOD)
    ]
    if not draft.supplier or any(field is None or field.value is None for field in values):
        return None
    supplier_id = draft.metadata.get("recognized_supplier", draft.supplier)
    return supplier_id, *(field.value for field in values if field is not None)


def _same_invoice(
    current: DocumentOutcome,
    prior: DocumentOutcome,
    keys: tuple[tuple[object, ...] | None, ...],
) -> bool:
    return set(keys) == {_invoice_identity(draft) for draft in prior.drafts} and _same_records(
        _invoice_values(current), _invoice_values(prior)
    )


def _same_records(left: list[dict[str, object]], right: list[dict[str, object]]) -> bool:
    unmatched = list(right)
    for record in left:
        for index, candidate in enumerate(unmatched):
            if record == candidate:
                unmatched.pop(index)
                break
        else:
            return False
    return not unmatched


def _mark_conflict(outcome: DocumentOutcome) -> None:
    outcome.status = DocumentOutcomeStatus.REQUIRES_REVIEW
    outcome.reason = "Aceeași identitate de factură are valori diferite."
    issue = ValidationIssue(
        field_id=None,
        severity=IssueSeverity.ERROR,
        message=outcome.reason,
        code=IssueCode.CONFLICTING_INVOICE,
    )
    if issue not in outcome.issues:
        outcome.issues += (issue,)


def _mark_dedupe_error(outcome: DocumentOutcome, error: Exception) -> None:
    outcome.status = DocumentOutcomeStatus.REQUIRES_REVIEW
    outcome.reason = f"Nu s-a putut verifica deduplicarea facturii: {error}"
    issue = ValidationIssue(
        field_id=None,
        severity=IssueSeverity.ERROR,
        message=outcome.reason,
        code=IssueCode.EXTRACTION_FAILED,
    )
    if issue not in outcome.issues:
        outcome.issues += (issue,)


def _invoice_values(outcome: DocumentOutcome) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for draft in outcome.drafts:
        records.append(
            {
                "identity": _invoice_identity(draft),
                "fields": {
                    name: (field.value, field.status) for name, field in draft.fields.items()
                },
                "price_details": tuple(
                    (
                        detail.category,
                        detail.description,
                        detail.source_quantity,
                        detail.source_unit,
                        detail.source_unit_price,
                        detail.normalized_quantity,
                        detail.normalized_unit,
                        detail.normalized_unit_price,
                        detail.net_value,
                    )
                    for detail in draft.price_details
                ),
            }
        )
    return records


@dataclass(frozen=True)
class ExtractedDocument:
    parser: SupplierParser | None
    drafts: tuple[InvoiceDraft, ...]


class ExtractInvoice:
    def __init__(self, parsers: Iterable[SupplierParser]) -> None:
        self._parsers = tuple(parsers)

    def execute(self, document: InputDocument) -> list[InvoiceDraft]:
        return list(self.execute_with_parser(document).drafts)

    def execute_with_parser(self, document: InputDocument) -> ExtractedDocument:
        for parser in self._parsers:
            if parser.recognizes(document):
                return ExtractedDocument(parser=parser, drafts=tuple(parser.parse(document)))
        issue = ValidationIssue(
            field_id=None,
            severity=IssueSeverity.ERROR,
            message=ISSUE_MESSAGES[IssueCode.UNSUPPORTED_SUPPLIER],
            code=IssueCode.UNSUPPORTED_SUPPLIER,
        )
        return ExtractedDocument(
            parser=None,
            drafts=(
                InvoiceDraft(
                    document_id=document.path.stem,
                    source_filename=document.path.name,
                    issues=[issue],
                ),
            ),
        )
