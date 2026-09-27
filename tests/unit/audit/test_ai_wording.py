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
        ("Textul a fost scris cu IA.", "IA"),
        ("Folosind inteligenţa artificială", "inteligenţa artificială"),
        ("Folosind inteligența artificială", "inteligența artificială"),
        ("Folosind inteligenţă artificială", "inteligenţă artificială"),
        ("folosind inteligenta artificiala", "inteligenta artificiala"),
        ("Un model de limbaj a redactat", "model de limbaj"),
        ("Modelul de limbaj a redactat", "Modelul de limbaj"),
        ("Scris cu ChatGPT.", "ChatGPT"),
        ("Scris cu GPT.", "GPT"),
        ("Scris cu Claude.", "Claude"),
        ("Scris cu Gemini.", "Gemini"),
        ("Scris cu OpenAI.", "OpenAI"),
        ("Un LLM a scris.", "LLM"),
        ("Text generat automat.", "generat automat"),
        ("Un asistent virtual a scris.", "asistent virtual"),
    ],
)
def test_ai_wording_is_found(text: str, found: str) -> None:
    assert ai_wording(text) == found
