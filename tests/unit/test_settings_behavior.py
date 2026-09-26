"""Provider settings stay local and handle availability checks explicitly."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ema.core.errors import EmaError
from ema.core.settings import read, update
from ema.core.settings import test_provider as check_provider
from ema.core.workspace import Workspace


def test_settings_update_merges_extraction_and_clears_provider(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    update(ws, {"default_provider": "gemini", "extraction": {"ocr": False}})

    result = update(ws, {"theme": "dark", "default_provider": None})

    assert result["theme"] == "dark"
    assert result["default_provider"] is None
    assert result["extraction"] == {
        "ocr": False,
        "flag_uncertain": True,
        "auto_accept_exact": False,
    }
    assert read(ws) == result


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"gemini_key": "secret"}, "key_not_allowed"),
        ({"gemini_api_key": "secret"}, "key_not_allowed"),
        ({"openai_api_key": "secret"}, "key_not_allowed"),
        ({"unsupported": True}, "settings_invalid"),
    ],
)
def test_settings_update_rejects_unknown_and_secret_values(
    tmp_path: Path, patch: dict[str, object], code: str
) -> None:
    with pytest.raises(EmaError) as error:
        update(Workspace(tmp_path), patch)
    assert error.value.code == code


def test_provider_rejects_unknown_and_reports_absent_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    monkeypatch.delenv("EMA_GEMINI_API_KEY", raising=False)
    with pytest.raises(EmaError) as invalid:
        check_provider(ws, "other")
    assert invalid.value.code == "provider_invalid"
    assert check_provider(ws, "gemini") == {"provider": "gemini", "status": "no_key"}


@pytest.mark.parametrize("status", [200, 503])
def test_provider_persists_only_successful_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    ws = Workspace(tmp_path)
    monkeypatch.setenv("EMA_OPENAI_API_KEY", "synthetic-key")

    class Response:
        status_code = status

    class Client:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def get(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setattr("ema.core.settings.httpx.Client", Client)
    result = check_provider(ws, "openai")
    assert result["status"] == ("ok" if status == 200 else "failed")
    assert bool(read(ws)["providers"]["openai"]["verified_at"]) is (status == 200)


def test_provider_network_error_is_reported_without_persisting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    monkeypatch.setenv("EMA_GEMINI_API_KEY", "synthetic-key")

    class Client:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def get(self, *_args: object, **_kwargs: object) -> None:
            raise httpx.ConnectError("offline")

    monkeypatch.setattr("ema.core.settings.httpx.Client", Client)
    assert check_provider(ws, "gemini") == {"provider": "gemini", "status": "failed"}
    assert read(ws)["providers"]["gemini"]["verified_at"] is None
