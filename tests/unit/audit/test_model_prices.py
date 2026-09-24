"""Curated text-token pricing, including cached and long-context input."""

from ema.core.llm.models import selected_model


def test_cached_input_uses_its_own_rate() -> None:
    model = selected_model("openai", "gpt-6-luna")
    assert model.cost(1_000_000, 1_000_000, 500_000) == 0.555


def test_gemini_pro_uses_long_prompt_prices() -> None:
    model = selected_model("gemini", "gemini-3.1-pro-preview")
    assert model.cost(200_000, 1_000, 100_000) == 0.232
    assert model.cost(200_001, 1_000, 100_000) > 0.44
