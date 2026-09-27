"""Provider keys remain in the OS store and API responses expose only a mask."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from keyring.errors import KeyringError

from ema.api import create_app
from ema.core.errors import EmaError
from ema.core.settings import (
    read,
    remove_provider_key,
    set_provider_key,
    settings_values,
    write_settings_values,
)
from ema.core.workspace import Workspace


def _client(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"),
        base_url="http://127.0.0.1:8766",
    )
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    return client, {"x-ema-csrf": token}


def test_key_routes_mask_default_delete_and_env_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        "ema.core.settings.keyring.set_password",
        lambda service, name, key: store.__setitem__((service, name), key),
    )
    monkeypatch.setattr(
        "ema.core.settings.keyring.delete_password",
        lambda service, name: store.pop((service, name), None),
    )
    monkeypatch.setattr(
        "ema.core.config.keyring.get_password", lambda service, name: store.get((service, name))
    )
    monkeypatch.delenv("EMA_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("EMA_OPENAI_API_KEY", raising=False)
    ws = Workspace(tmp_path / "workspace")
    client, headers = _client(ws)
    secret = "AIza1234567Kd2"
    response = client.put("/settings/providers/gemini/key", json={"key": secret}, headers=headers)
    assert response.status_code == 204
    assert store[("Ema", "gemini_api_key")] == secret
    assert secret not in ws.settings_text()
    view = client.get("/settings").json()
    assert view["default_provider"] == "gemini"
    assert view["providers"]["gemini"] == {
        "present": True,
        "verified_at": None,
        "hint": "AIza••••••••7Kd2",
        "source": "keyring",
    }
    values = settings_values(ws)
    values["provider_verified"] = {"gemini": "2026-09-27T08:00:00+00:00"}
    write_settings_values(ws, values)
    assert (
        client.put(
            "/settings/providers/gemini/key", json={"key": secret}, headers=headers
        ).status_code
        == 204
    )
    assert client.get("/settings").json()["providers"]["gemini"]["verified_at"] is None
    assert (
        client.put(
            "/settings/providers/openai/key", json={"key": "sk-short"}, headers=headers
        ).status_code
        == 204
    )
    assert client.get("/settings").json()["providers"]["openai"]["hint"] == "••••••••"
    log = ws.root / "logs" / "ema.jsonl"
    assert (
        secret
        not in response.text
        + client.get("/settings").text
        + (log.read_text() if log.exists() else "")
        + caplog.text
    )
    monkeypatch.setenv("EMA_GEMINI_API_KEY", "ENVabcdefg1234")
    assert read(ws)["providers"]["gemini"]["source"] == "environment"
    monkeypatch.delenv("EMA_GEMINI_API_KEY")
    assert client.delete("/settings/providers/gemini/key", headers=headers).status_code == 204
    assert client.get("/settings").json()["providers"]["gemini"]["hint"] is None
    assert client.get("/settings").json()["default_provider"] == "openai"
    assert client.delete("/settings/providers/gemini/key", headers=headers).status_code == 204
    assert client.delete("/settings/providers/openai/key", headers=headers).status_code == 204
    assert client.get("/settings").json()["default_provider"] is None


@pytest.mark.parametrize("key", ["", " ", "a b", "x" * 513])
def test_key_input_is_422(tmp_path: Path, key: str) -> None:
    client, headers = _client(Workspace(tmp_path))
    assert (
        client.put("/settings/providers/gemini/key", json={"key": key}, headers=headers).status_code
        == 422
    )


def test_unknown_provider_and_keyring_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ws = Workspace(tmp_path)
    client, headers = _client(ws)
    assert (
        client.put(
            "/settings/providers/other/key", json={"key": "synthetic"}, headers=headers
        ).status_code
        == 400
    )
    secret = "synthetic-planted-secret"
    monkeypatch.setattr(
        "ema.core.settings.keyring.set_password",
        lambda *_args: (_ for _ in ()).throw(KeyringError(secret)),
    )
    failed = client.put("/settings/providers/gemini/key", json={"key": secret}, headers=headers)
    assert failed.status_code == 424
    log = ws.root / "logs" / "ema.jsonl"
    assert secret not in failed.text + caplog.text + log.read_text()
    with pytest.raises(EmaError) as error:
        set_provider_key(ws, "gemini", "synthetic")
    assert error.value.code == "keyring_unavailable"
    monkeypatch.setattr(
        "ema.core.settings.keyring.delete_password",
        lambda *_args: (_ for _ in ()).throw(KeyringError()),
    )
    assert client.delete("/settings/providers/gemini/key", headers=headers).status_code == 424


def test_keyring_set_does_not_hold_workspace_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    events: list[str] = []

    @contextmanager
    def lock(_root: Path) -> Iterator[None]:
        events.append("lock")
        yield
        events.append("unlock")

    monkeypatch.setattr("ema.core.settings.workspace_lock", lock)
    monkeypatch.setattr(
        "ema.core.settings.keyring.set_password", lambda *_: events.append("keyring")
    )
    set_provider_key(ws, "gemini", "synthetic")
    assert events == ["keyring", "lock", "unlock"]


def test_delete_does_not_run_before_other_provider_read_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    write_settings_values(
        ws, {"provider": "gemini", "provider_verified": {"gemini": "2026-09-27T08:00:00Z"}}
    )
    deleted: list[str] = []
    monkeypatch.setattr(
        "ema.core.settings.keyring.delete_password", lambda _service, name: deleted.append(name)
    )
    monkeypatch.setattr(
        "ema.core.config.keyring.get_password",
        lambda *_: (_ for _ in ()).throw(KeyringError("synthetic read failure")),
    )
    with pytest.raises(EmaError) as error:
        remove_provider_key(ws, "gemini")
    assert error.value.code == "keyring_unavailable"
    assert deleted == []
    assert settings_values(ws)["provider_verified"]["gemini"] == "2026-09-27T08:00:00Z"
