"""Errors at the Office boundary."""

from ema.core.errors import EmaError

_USER_MESSAGES_RO = {
    "word_permission": (
        "În Configurări sistem → Confidențialitate și securitate → Automatizare, "
        "permiteți aplicației care rulează Ema să controleze Microsoft Word."
    ),
    "word_missing": "Microsoft Word nu este instalat sau configurat.",
    "word_timeout": "Microsoft Word nu a răspuns la timp. Încercați din nou.",
    "word_automation": "Operația din Microsoft Word a eșuat.",
    "word_restart": "Microsoft Word nu a putut fi repornit în siguranță.",
    "word_launch": "Automatizarea Microsoft Word nu a putut fi pornită.",
    "word_pdf": "Microsoft Word nu a creat fișierul PDF.",
    "chart_formula": "Formula seriei din grafic nu este validă.",
    "chart_cache": "Datele memorate ale graficului lipsesc.",
    "chart_location": "Graficul nu a fost găsit în document.",
    "chart_series": "Seriile graficului nu corespund datelor sursă.",
    "chart_title": "Titlul graficului nu a putut fi actualizat.",
    "chart_style": "Stilul graficului nu a putut fi preluat.",
    "label_missing": "Eticheta nu a fost găsită în foaia de calcul.",
    "label_ambiguous": "Eticheta apare de mai multe ori în foaia de calcul.",
    "formula_uncached": "Formula din foaia de calcul nu are o valoare memorată.",
    "cell_error": "Celula conține o eroare Excel.",
    "mixed_run_replacement": "Textul nu poate fi aliniat la formatarea modelului.",
    "sheet_missing": "Foaia de calcul nu a fost găsită.",
    "unsupported_format": "Formatul fișierului nu este acceptat.",
    "numbering_conflict": "Numerotarea figurilor sau tabelelor este în conflict.",
    "block_reference": "Referința la figură sau tabel nu a fost găsită.",
    "block_prototype": "Modelul de document lipsește sau nu este valid.",
}


class OfficeError(EmaError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, _USER_MESSAGES_RO[code], detail)
