from __future__ import annotations

from typing import Protocol

from ema.invoices.models import InputDocument, InvoiceDraft


class SupplierParser(Protocol):
    supplier_name: str
    layout_version: str
    document_type: str

    def recognizes(self, document: InputDocument) -> bool: ...

    def parse(self, document: InputDocument) -> list[InvoiceDraft]: ...
