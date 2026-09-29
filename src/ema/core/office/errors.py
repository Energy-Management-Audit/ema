"""Errors at the Office boundary."""

from ema.core.errors import EmaError

_USER_MESSAGES_RO = {
    "word_permission": (
        "În Configurări sistem → Confidenţialitate şi securitate → Automatizare, "
        "permiteţi aplicaţiei care rulează Ema să controleze Microsoft Word."
    ),
    "word_missing": "Microsoft Word nu este instalat sau configurat.",
    "word_timeout": "Microsoft Word nu a răspuns la timp. Încercaţi din nou.",
    "word_automation": "Operaţia din Microsoft Word a eşuat.",
    "word_restart": "Microsoft Word nu a putut fi repornit în siguranţă.",
    "word_launch": "Automatizarea Microsoft Word nu a putut fi pornită.",
    "word_pdf": "Microsoft Word nu a creat fişierul PDF.",
    "word_docx": "Microsoft Word nu a creat fişierul DOCX.",
    "word_text": "Microsoft Word nu a extras textul documentului.",
    "word_kill": "Microsoft Word nu a putut fi oprit în siguranţă.",
    "chart_formula": "Formula seriei din grafic nu este validă.",
    "chart_cache": "Datele memorate ale graficului lipsesc.",
    "chart_location": "Graficul nu a fost găsit în document.",
    "chart_series": "Seriile graficului nu corespund datelor sursă.",
    "chart_title": "Titlul graficului nu a putut fi actualizat.",
    "chart_style": "Stilul graficului nu a putut fi preluat.",
    "label_missing": "Eticheta nu a fost găsită în foaia de calcul.",
    "label_ambiguous": "Eticheta apare de mai multe ori în foaia de calcul.",
    "formula_uncached": "Formula din foaia de calcul nu are o valoare memorată.",
    "cell_error": "Celula conţine o eroare Excel.",
    "mixed_run_replacement": "Textul nu poate fi aliniat la formatarea modelului.",
    "sheet_missing": "Foaia de calcul nu a fost găsită.",
    "unsupported_format": "Formatul fişierului nu este acceptat.",
    "numbering_conflict": "Numerotarea figurilor sau tabelelor este în conflict.",
    "block_reference": "Referinţa la figură sau tabel nu a fost găsită.",
    "block_prototype": "Modelul de document lipseşte sau nu este valid.",
}


class OfficeError(EmaError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, _USER_MESSAGES_RO.get(code, "Operaţia Office a eşuat."), detail)
