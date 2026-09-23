from enum import StrEnum


class WorkbookExportError(RuntimeError):
    """Base error for a workbook that could not be delivered safely."""


class WorkbookWriteError(WorkbookExportError):
    """The temporary workbook could not be written and closed."""


class WorkbookVerificationError(WorkbookExportError):
    """The temporary workbook did not satisfy the approved contract."""


class WorkbookVerificationCode(StrEnum):
    UNREADABLE = "UNREADABLE"
    SHEETS = "SHEETS"
    SUMMARY_HEADERS = "SUMMARY_HEADERS"
    DETAIL_HEADERS = "DETAIL_HEADERS"
    SUMMARY_ROW_COUNT = "SUMMARY_ROW_COUNT"
    DETAIL_ROW_COUNT = "DETAIL_ROW_COUNT"
    LINK_IDENTIFIERS = "LINK_IDENTIFIERS"
    FORMULAS = "FORMULAS"
    NUMBER_FORMATS = "NUMBER_FORMATS"
    NEGATIVE_FORMATTING = "NEGATIVE_FORMATTING"


class WorkbookContractError(WorkbookVerificationError):
    """A stable workbook-contract verification failure."""

    def __init__(self, code: WorkbookVerificationCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class WorkbookCommitError(WorkbookExportError):
    """The verified workbook could not atomically replace the destination."""


class WorkbookCleanupError(WorkbookExportError):
    """A known temporary workbook could not be removed."""
