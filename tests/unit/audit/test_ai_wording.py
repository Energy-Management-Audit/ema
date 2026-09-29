"""One rule for AI wording, shared by the draft check and the final gate."""

from __future__ import annotations

import pytest

from ema.audit.ai_wording import ai_wording


@pytest.mark.parametrize(
    "text",
    [
        "Specialişti angajaţi ai unor persoane juridice.",
        "Se ia în calcul consumul anual.",
        "Ai editat ciorna în Word.",
        "Iată consumurile, iar ia seama la pierderi.",
        "Detalii despre instalaţia de aer comprimat.",
    ],
)
def test_romanian_ai_and_ia_pass(text: str) -> None:
    assert ai_wording(text) is None


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Acest raport a fost generat de AI", "AI"),
        ("Text generat cu IA.", "IA"),
        ("Folosind inteligenţa artificială", "inteligenţa artificială"),
        ("Folosind inteligența artificială", "inteligența artificială"),
        ("Folosind inteligenţă artificială", "inteligenţă artificială"),
        ("folosind inteligenta artificiala", "inteligenta artificiala"),
        ("Un model de limbaj a redactat", "model de limbaj"),
        ("Modelul de limbaj a redactat", "Modelul de limbaj"),
        ("Scris cu ChatGPT.", "ChatGPT"),
        ("Scris cu GPT-5.", "GPT-5"),
        ("Asistentul Claude.", "Claude"),
        ("Un algoritm Gemini.", "Gemini"),
        ("Scris cu OpenAI.", "OpenAI"),
        ("Un LLM a scris.", "LLM"),
        ("Text generat automat.", "generat automat"),
        ("Un asistent virtual a scris.", "asistent virtual"),
    ],
)
def test_ai_wording_is_found(text: str, found: str) -> None:
    assert ai_wording(text) == found


@pytest.mark.parametrize(
    "text",
    [
        "inteligenţei artificiale",
        "inteligenței artificiale",
        "inteligențelor artificiale",
        "generată automat",
        "generate automat",
        "Generarea automată a raportului.",
        "Generarea automată a fost realizată de Gemini.",
        "Algoritmul de calcul folosește IA pentru clasificare.",
        "modelului de limbaj",
        "model lingvistic",
        "modele lingvistice",
        "asistentul virtual",
        "Copilot",
        "GPT4",
        "gpt-5",
        "Un asistent Claude",
        "Generarea cu Gemini",
        "Automatizarea cu AI",
        "Inteligenței Claude",
        "Generat cu AI",
        "Un algoritm IA",
    ],
)
def test_f5_inflections_and_context_are_refused(text: str) -> None:
    assert ai_wording(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "8 AI şi 4 AO",
        "Jean-Claude",
        "Echipament Gemini",
        "ANGAJATI AI COMPANIEI",
        "Secţia IA",
        "Claude a verificat instalaţia.",
        "Pompa model Gemini 40",
        "Modelele noastre includ un modul Gemini",
        "Model Claude.",
        "Algoritmul verificat. Gemini este marca pompei.",
        "Algoritmul verificat! 8 AI şi 4 AO.",
        "Algoritmul verificat? Secţia IA.",
        "Generat din măsurători; angajaţi ai companiei.",
        "Scris cu GPT.",
    ],
)
def test_f5_industrial_names_and_separate_sentences_pass(text: str) -> None:
    assert ai_wording(text) is None
