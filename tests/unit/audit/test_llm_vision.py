"""Image references are hashed; bytes travel only through provider attachments."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel
from tests.workspace_jobs import create_job

from ema.core.llm.agent import AgentContext
from ema.core.llm.models import curated_models
from ema.core.llm.providers import GeminiProvider, _openai_messages
from ema.core.llm.recording import RecordingProvider
from ema.core.llm.replay import ReplayProvider, request_hashes
from ema.core.llm.structured import complete_json
from ema.core.llm.types import Exchange, ImageInput, ToolSpec
from ema.core.workspace import Workspace


class Answer(BaseModel):
    value: str


class FakeProvider:
    name = "gemini"

    def respond(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: tuple[ToolSpec, ...],
        schema: dict[str, Any] | None = None,
        max_output_tokens: int = 4096,
        synthetic: bool = False,
        *,
        prompt_version: str = "",
        attachments: dict[str, bytes] | None = None,
        thinking_tokens: int | None = None,
    ) -> Exchange:
        assert attachments == {"a" * 64: b"image bytes"}
        return Exchange('{"value":"read"}', (), 10, 2)


def test_model_catalogue_requires_vision_flag() -> None:
    assert all(model.vision for model in curated_models())


def test_hash_uses_image_sha_not_bytes_and_recording_replays(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    recording = tmp_path / "recording.json"
    provider = RecordingProvider(FakeProvider(), recording)
    context = AgentContext(
        ws, job, "readings", provider, "gemini-3.6-flash", "audit-meter-v1", True
    )
    image = ImageInput("a" * 64, "image/png", b"image bytes")
    assert (
        complete_json(context, Answer, "Read", "Photo: synthetic.png", images=(image,)).value
        == "read"
    )
    recorded = json.loads(recording.read_text(encoding="utf-8"))
    assert recorded["source"] == "recorded"
    assert "image bytes" not in recording.read_text(encoding="utf-8")
    replay = ReplayProvider(recording)
    assert replay.source == "recorded"
    messages = [
        {"role": "system", "content": "Read"},
        {
            "role": "user",
            "content": "Photo: synthetic.png",
            "images": [{"sha256": "a" * 64, "media_type": "image/png"}],
        },
    ]
    first = request_hashes(
        "gemini-3.6-flash", messages, (), Answer.model_json_schema(), 4096, "audit-meter-v1"
    )
    assert first == recorded["responses"][0]["request_hashes"]
    assert (
        replay.respond(
            "gemini-3.6-flash",
            messages,
            (),
            Answer.model_json_schema(),
            prompt_version="audit-meter-v1",
            attachments={"a" * 64: b"different bytes"},
        ).text
        == '{"value":"read"}'
    )


def test_thinking_budget_does_not_change_recording_hash(tmp_path: Path) -> None:
    class DraftProvider:
        name = "gemini"

        def __init__(self) -> None:
            self.thinking: list[int | None] = []

        def respond(self, *args: Any, **kwargs: Any) -> Exchange:
            self.thinking.append(kwargs.get("thinking_tokens"))
            return Exchange('{"value":"read"}', (), 1, 1, finish_reason="MAX_TOKENS")

    inner = DraftProvider()
    recording = tmp_path / "recording.json"
    provider = RecordingProvider(inner, recording)
    messages = [{"role": "user", "content": "synthetic draft"}]
    for thinking in (None, 16_000):
        provider.respond("gemini-3.6-flash", messages, (), synthetic=True, thinking_tokens=thinking)
    rows = json.loads(recording.read_text(encoding="utf-8"))["responses"]
    assert rows[0]["request_hashes"] == rows[1]["request_hashes"]
    assert rows[0]["candidates"][0]["finishReason"] == "MAX_TOKENS"
    replay = ReplayProvider(recording)
    assert (
        replay.respond("gemini-3.6-flash", messages, (), thinking_tokens=16_000).finish_reason
        == "MAX_TOKENS"
    )
    assert inner.thinking == [None, 16_000]


def test_openai_and_gemini_convert_images_without_forwarding_hash_key() -> None:
    messages = [
        {
            "role": "user",
            "content": "Read",
            "images": [{"sha256": "sha", "media_type": "image/png"}],
        }
    ]
    converted = _openai_messages(messages, {"sha": b"png"})
    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Read"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,cG5n"}},
            ],
        }
    ]

    captured: dict[str, Any] = {}

    def generate_content(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(
            text="{}",
            function_calls=[],
            candidates=[],
            usage_metadata=None,
        )

    provider = GeminiProvider.__new__(GeminiProvider)
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))  # type: ignore[assignment]
    provider.respond("gemini-3.6-flash", messages, (), synthetic=True, attachments={"sha": b"png"})
    parts = captured["contents"][0].parts
    assert parts[0].text == "Read"
    assert parts[1].inline_data.data == b"png"
