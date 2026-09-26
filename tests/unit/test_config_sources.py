"""Settings precedence and secret boundaries."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest
from keyring.errors import KeyringLocked, NoKeyringError

from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.llm.providers import GeminiProvider, OpenAIProvider
from ema.core.settings import read
from ema.core.settings import test_provider as check_provider
from ema.core.workspace import Workspace


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EMA_GEMINI_API_KEY", "EMA_OPENAI_API_KEY", "EMA_LLM_LIVE"):
        monkeypatch.delenv(name, raising=False)


def test_environment_overrides_workspace_and_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    monkeypatch.delenv("EMA_WORD_TIMEOUT_S", raising=False)
    assert load_settings(ws).word_timeout_s == 120

    ws.settings_file().write_text("word_timeout_s = 30\n")
    assert load_settings(ws).word_timeout_s == 30

    monkeypatch.setenv("EMA_WORD_TIMEOUT_S", "7")
    assert load_settings(ws).word_timeout_s == 7


def test_bad_workspace_settings_keep_error_code(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    ws.settings_file().write_text("word_timeout_s = -1\n")
    with pytest.raises(EmaError) as invalid:
        load_settings(ws)
    assert invalid.value.code == "settings_invalid"
    assert "spaţiului de lucru" in invalid.value.user_message_ro


@pytest.mark.parametrize("name", ["EMA_LLM_LIVE", "EMA_WORD_TIMEOUT_S"])
def test_empty_environment_value_uses_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "")
    ws = Workspace(tmp_path)
    configured = load_settings(ws)
    assert configured.llm_live is False
    assert configured.word_timeout_s == 120
    assert read(ws)["providers"]["gemini"]["present"] is False


@pytest.mark.parametrize("name", ["EMA_LLM_LIVE", "EMA_WORD_TIMEOUT_S"])
def test_malformed_environment_value_names_its_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "bogus")
    with pytest.raises(EmaError) as invalid:
        load_settings(Workspace(tmp_path))
    assert invalid.value.code == "settings_invalid"
    assert name in invalid.value.user_message_ro
    assert name in invalid.value.detail


def test_keys_use_environment_then_keyring_and_ignore_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    ws.settings_file().write_text('gemini_api_key = "workspace-secret"\nllm_live = true\n')
    assert load_settings(ws).provider_key("gemini") is None
    assert load_settings(ws).llm_live is False

    monkeypatch.setattr(
        "ema.core.config.keyring.get_password",
        lambda service, name: (
            "keyring-secret" if (service, name) == ("Ema", "gemini_api_key") else None
        ),
    )
    assert load_settings(ws).provider_key("gemini").get_secret_value() == "keyring-secret"

    monkeypatch.setenv("EMA_GEMINI_API_KEY", "environment-secret")
    assert load_settings(ws).provider_key("gemini").get_secret_value() == "environment-secret"
    monkeypatch.setenv("EMA_LLM_LIVE", "true")
    assert load_settings(ws).llm_live is True


def test_missing_keyring_key_means_no_key(tmp_path: Path) -> None:
    assert load_settings(Workspace(tmp_path)).provider_key("gemini") is None


def test_no_keyring_backend_means_no_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*_args: object) -> None:
        raise NoKeyringError("no backend")

    monkeypatch.setattr("ema.core.config.keyring.get_password", unavailable)
    configured = load_settings(Workspace(tmp_path))
    assert configured.provider_key("gemini") is None


@pytest.mark.parametrize("failure", [KeyringLocked("locked"), Exception("boom")])
def test_keyring_failure_surfaces_with_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def unavailable(*_args: object) -> None:
        raise failure

    monkeypatch.setattr("ema.core.config.keyring.get_password", unavailable)
    configured = load_settings(Workspace(tmp_path))
    with pytest.raises(EmaError) as raised:
        configured.provider_key("gemini")
    assert raised.value.code == "keyring_unavailable"
    assert type(failure).__name__ in raised.value.detail
    assert str(failure) in raised.value.detail


def test_keyring_is_not_read_until_missing_key_is_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def lookup(_service: str, name: str) -> str:
        calls.append(name)
        raise Exception("boom")

    monkeypatch.setattr("ema.core.config.keyring.get_password", lookup)
    monkeypatch.setenv("EMA_GEMINI_API_KEY", "environment-secret")
    configured = load_settings(Workspace(tmp_path))
    assert calls == []
    assert configured.provider_key("gemini").get_secret_value() == "environment-secret"
    assert calls == []
    with pytest.raises(EmaError) as raised:
        configured.provider_key("openai")
    assert raised.value.code == "keyring_unavailable"
    assert calls == ["openai_api_key"]


def test_secret_never_appears_in_settings_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("EMA_GEMINI_API_KEY", "synthetic-secret-text")
    configured = load_settings(Workspace(tmp_path))
    logging.getLogger(__name__).warning("%s", configured)
    for rendered in (repr(configured), str(configured), repr(configured.model_dump()), caplog.text):
        assert "synthetic-secret-text" not in rendered


@pytest.mark.parametrize(
    ("provider_type", "environment"),
    [
        (GeminiProvider, "EMA_GEMINI_API_KEY"),
        (OpenAIProvider, "EMA_OPENAI_API_KEY"),
    ],
)
def test_live_gate_and_provider_use_same_settings_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_type: type[GeminiProvider] | type[OpenAIProvider],
    environment: str,
) -> None:
    ws = Workspace(tmp_path)
    monkeypatch.setenv(environment, "synthetic-key")
    configured = load_settings(ws)
    with pytest.raises(EmaError) as offline:
        provider_type(configured.provider_key(provider_type.name), configured.llm_live)
    assert offline.value.code == "ai_offline"

    monkeypatch.setenv("EMA_LLM_LIVE", "true")
    monkeypatch.delenv(environment)
    configured = load_settings(ws)
    with pytest.raises(EmaError) as missing:
        provider_type(configured.provider_key(provider_type.name), configured.llm_live)
    assert missing.value.code == "ai_key_missing"
    assert missing.value.detail == environment

    monkeypatch.setenv(environment, "synthetic-key")
    configured = load_settings(ws)
    constructed: list[str] = []
    if provider_type is GeminiProvider:
        monkeypatch.setattr(
            "ema.core.llm.providers.genai.Client",
            lambda **kwargs: constructed.append(kwargs["api_key"]),
        )
    else:
        monkeypatch.setattr(
            "ema.core.llm.providers.OpenAI",
            lambda **kwargs: constructed.append(kwargs["api_key"]),
        )
    provider_type(configured.provider_key(provider_type.name), configured.llm_live)
    assert constructed == ["synthetic-key"]
    assert read(ws)["providers"][provider_type.name]["present"] is True


def test_provider_check_uses_keyring_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = Workspace(tmp_path)
    monkeypatch.setattr(
        "ema.core.config.keyring.get_password",
        lambda service, name: "synthetic-key" if name == "openai_api_key" else None,
    )

    class Client:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def get(self, *_args: object, **kwargs: object) -> object:
            assert kwargs["headers"] == {"Authorization": "Bearer synthetic-key"}
            return type("Response", (), {"status_code": 200})()

    monkeypatch.setattr("ema.core.settings.httpx.Client", Client)
    assert check_provider(ws, "openai")["status"] == "ok"
    assert read(ws)["providers"]["openai"]["present"] is True


def test_application_does_not_read_api_keys_or_live_flag_from_os_environ() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src" / "ema"
    forbidden = {
        "EMA_GEMINI_API_KEY",
        "EMA_OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "EMA_LLM_LIVE",
    }

    def is_environ(node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "environ"
        )

    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
                assert not (
                    node.func.attr == "get"
                    and is_environ(node.func.value)
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value in forbidden
                ), path
                assert not (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                    and node.func.attr == "getenv"
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value in forbidden
                ), path
            if isinstance(node, ast.Subscript):
                assert not (
                    is_environ(node.value)
                    and isinstance(node.slice, ast.Constant)
                    and node.slice.value in forbidden
                ), path
