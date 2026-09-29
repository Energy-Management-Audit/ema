"""Invoice parser composition, shared by the CLI and stage."""

from __future__ import annotations

from ema.core.config import Settings
from ema.invoices.parsers.alive_parser import AliveInvoiceParser
from ema.invoices.parsers.eds_parser import EdsInvoiceParser
from ema.invoices.parsers.engie_parser import EngieInvoiceParser
from ema.invoices.parsers.hidroelectrica_ppc_parser import (
    EnelPpcInvoiceParser,
    HidroelectricaInvoiceParser,
)
from ema.invoices.parsers.incompatible_parser import (
    EngieEInvoiceCompanionParser,
    MetNaturalGasInvoiceParser,
    SeeExclusiveRefactoringParser,
)
from ema.invoices.parsers.met_energy_parser import (
    MetElectricityInvoiceParser,
)
from ema.invoices.parsers.next_energy_parser import NextEnergyInvoiceParser
from ema.invoices.parsers.omv_petrom_parser import OmvPetromInvoiceParser
from ema.invoices.parsers.reinvoicing_supplier_parser import (
    ElectricPlannersInvoiceParser,
    GeticaInvoiceParser,
)
from ema.invoices.pipeline import ExtractInvoice, ProcessInvoiceFiles
from ema.invoices.reader import InvoiceDocumentReader


def build_invoice_processor(settings: Settings) -> ProcessInvoiceFiles:
    return ProcessInvoiceFiles(
        InvoiceDocumentReader(settings),
        ExtractInvoice(
            [
                EngieInvoiceParser(),
                EngieEInvoiceCompanionParser(),
                OmvPetromInvoiceParser(),
                AliveInvoiceParser(),
                EdsInvoiceParser(),
                MetElectricityInvoiceParser(),
                MetNaturalGasInvoiceParser(),
                SeeExclusiveRefactoringParser(),
                NextEnergyInvoiceParser(),
                HidroelectricaInvoiceParser(),
                EnelPpcInvoiceParser(),
                GeticaInvoiceParser(),
                ElectricPlannersInvoiceParser(),
            ]
        ),
    )
