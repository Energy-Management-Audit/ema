"""Synthetic fixtures use the first curated vision model for their provider."""

from ema.core.llm.models import curated_models

REPLAY_MODEL = next(model.id for model in curated_models() if model.provider == "gemini")
