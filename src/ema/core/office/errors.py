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
}


class OfficeError(EmaError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, _USER_MESSAGES_RO[code], detail)
