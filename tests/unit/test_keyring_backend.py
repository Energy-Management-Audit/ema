"""Explicit backend choice in an environment without entry points."""

from unittest.mock import Mock

import pytest

from ema import cli
from ema.core import keyring_backend


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("win32", "WinVaultKeyring"), ("darwin", "Keyring"), ("linux", "Keyring")],
)
def test_platform_backend(monkeypatch: pytest.MonkeyPatch, platform: str, expected: str) -> None:
    monkeypatch.setattr(keyring_backend.sys, "platform", platform)
    chosen = Mock()
    monkeypatch.setattr(keyring_backend.keyring, "set_keyring", chosen)
    keyring_backend.install_keyring()
    assert chosen.call_args.args[0].__class__.__name__ == expected
    assert chosen.call_args.args[0].__class__.__module__.endswith(
        {"win32": "Windows", "darwin": "macOS", "linux": "fail"}[platform]
    )


def test_cli_installs_before_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "install_keyring", lambda: calls.append("keyring"))
    monkeypatch.setattr("ema.cli._app", lambda: calls.append("dispatch"))
    cli.app()
    assert calls == ["keyring", "dispatch"]
