"""Release-curated model and price data."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field

from ema.core.errors import EmaError
from ema.core.resources import resource_path


@dataclass(frozen=True)
class Model:
    provider: str
    id: str
    tier: str
    vision: bool
    input_usd: float
    cached_input_usd: float
    output_usd: float
    long_input_usd: float | None = None
    long_cached_input_usd: float | None = None
    long_output_usd: float | None = None
    request_options: dict[str, str] = field(default_factory=dict[str, str])

    def cost(self, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> float:
        if not 0 <= cached_input_tokens <= input_tokens:
            raise ValueError("cached input tokens exceed input tokens")
        long = input_tokens > 200_000 and self.long_input_usd is not None
        input_rate = self.long_input_usd if long else self.input_usd
        cached_rate = self.long_cached_input_usd if long else self.cached_input_usd
        output_rate = self.long_output_usd if long else self.output_usd
        assert input_rate is not None and cached_rate is not None and output_rate is not None
        return (
            (input_tokens - cached_input_tokens) * input_rate
            + cached_input_tokens * cached_rate
            + output_tokens * output_rate
        ) / 1_000_000


def curated_models() -> tuple[Model, ...]:
    with resource_path("llm", "models.toml").open("rb") as handle:
        values = tomllib.load(handle)
    return tuple(Model(**entry) for entry in values["models"])


def selected_model(provider: str, model_id: str) -> Model:
    for model in curated_models():
        if (model.provider, model.id) == (provider, model_id):
            return model
    raise EmaError("model_unknown", "Modelul ales nu este disponibil.", provider)


def default_model(provider: str) -> Model:
    """The provider's first standard-tier model in the release list."""
    for model in curated_models():
        if model.provider == provider and model.tier == "standard":
            return model
    raise EmaError("model_unknown", "Modelul ales nu este disponibil.", provider)
