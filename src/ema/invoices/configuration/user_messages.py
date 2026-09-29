from __future__ import annotations

from ema.invoices.export.errors import (
    WorkbookCleanupError,
    WorkbookCommitError,
    WorkbookExportError,
    WorkbookVerificationError,
    WorkbookWriteError,
)
from ema.invoices.models import IssueCode

WINDOW_TITLE = "EMA — Extragere facturi de energie"
MAIN_HEADING = "Extragere facturi de energie"
MAIN_SUBTITLE = (
    "Procesare locală pentru facturi PDF cu text integrat sau pagini scanate. "
    "OCR-ul local este folosit când este necesar. Se generează câte un rezultat "
    "pentru fiecare loc de consum, iar documentele incompatibile sunt raportate."
)
FILE_DIALOG_TITLE = "Selectează facturi de energie"
PROCESSING_STARTED = "Se procesează local toate paginile facturilor selectate…"

EXPORT_ERROR_MESSAGES: dict[type[WorkbookExportError], str] = {
    WorkbookWriteError: "Fişierul Excel temporar nu a putut fi scris în siguranţă.",
    WorkbookVerificationError: (
        "Fişierul Excel generat nu a trecut verificarea şi nu a înlocuit destinaţia."
    ),
    WorkbookCommitError: (
        "Fişierul Excel a fost verificat, dar nu a putut înlocui destinaţia aleasă."
    ),
    WorkbookCleanupError: "Fişierul Excel temporar nu a putut fi eliminat.",
}

ISSUE_MESSAGES: dict[IssueCode, str] = {
    IssueCode.UNSUPPORTED_SUPPLIER: (
        "Factura nu a fost recunoscută de niciun parser de furnizor disponibil."
    ),
    IssueCode.DUPLICATE_DOCUMENT: ("Documentul duplicat a fost exclus din export."),
    IssueCode.INCOMPATIBLE_DOCUMENT_TYPE: (
        "Documentul a fost recunoscut, dar nu este compatibil cu centralizatorul de electricitate."
    ),
    IssueCode.MISSING_LOCATION_IDENTIFIER: (
        "Codul locului de consum nu a putut fi identificat şi trebuie completat manual."
    ),
    IssueCode.MISSING_METER_IDENTIFIER: (
        "Seria contorului nu a putut fi identificată şi trebuie completată manual."
    ),
    IssueCode.MISSING_CONSUMPTION_PERIOD: (
        "Perioada segmentului de consum nu a putut fi identificată şi trebuie completată manual."
    ),
    IssueCode.AMBIGUOUS_INVOICE_NUMBER: (
        "Numărul facturii este ambiguu şi trebuie confirmat manual."
    ),
    IssueCode.INVALID_PRICE_RECONCILIATION: (
        "Preţurile şi valorile facturate nu se reconciliază şi trebuie verificate."
    ),
    IssueCode.OCR_RUNTIME_UNAVAILABLE: (
        "Factura necesită OCR local, dar componenta Tesseract nu este disponibilă."
    ),
    IssueCode.OCR_TIMEOUT: "OCR-ul a depăşit timpul permis pentru această factură.",
    IssueCode.PDF_READ_FAILED: "Fişierul PDF nu a putut fi citit sau procesat.",
    IssueCode.EXTRACTION_FAILED: (
        "Factura a fost citită, dar datele nu au putut fi extrase în siguranţă."
    ),
    IssueCode.MISSING_CLIENT_IDENTITY: (
        "Denumirea clientului nu a putut fi identificată şi trebuie completată manual."
    ),
    IssueCode.AMBIGUOUS_CLIENT_IDENTITY: (
        "Identitatea clientului este ambiguă şi trebuie confirmată manual."
    ),
}
