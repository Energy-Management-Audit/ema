"""The installed bundle's JSON diagnostics remain machine-readable on failure."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from ema import cli
from ema.cli import _app

install_check = import_module("ema.cli.install_check")
ROOT = Path(__file__).resolve().parents[2]


def test_resource_manifest_is_exactly_the_tracked_tree_plus_frontend() -> None:
    tracked = subprocess.check_output(["git", "ls-files", "resources"], cwd=ROOT, text=True)
    expected = {line.removeprefix("resources/") for line in tracked.splitlines()}
    expected.add("frontend/index.html")
    actual = {"/".join(parts) for parts in install_check.RESOURCE_FILES}
    assert actual == expected


def test_checks_mark_word_optional_and_webview2_required_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for parts in install_check.RESOURCE_FILES:
        file = tmp_path.joinpath(*parts)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"synthetic")
    monkeypatch.setattr(install_check, "resource_path", tmp_path.joinpath)
    monkeypatch.setattr(install_check, "workspace_path", lambda: tmp_path / "workspace")
    monkeypatch.setattr(install_check.sys, "platform", "win32")
    monkeypatch.setattr(
        install_check, "load_settings", lambda _ws: SimpleNamespace(word_path=tmp_path / "Word.exe")
    )
    monkeypatch.setattr(
        install_check.pdf, "ocr", lambda *_args: [SimpleNamespace(text="energie electrică")]
    )
    monkeypatch.setattr(install_check, "webview2_version", lambda: None, raising=False)

    def backend() -> install_check.WinVaultKeyring:
        return install_check.WinVaultKeyring()

    monkeypatch.setattr(install_check.keyring, "get_keyring", backend)
    result = install_check.check_install()
    checks = {item["name"]: item for item in result["checks"]}
    assert list(checks) == ["resources", "workspace", "ocr", "webview2", "keyring", "word"]
    assert all(checks[name]["ok"] for name in ("resources", "workspace", "ocr"))
    assert checks["webview2"]["required"] and not checks["webview2"]["ok"]
    assert checks["keyring"] == {
        "name": "keyring",
        "ok": True,
        "required": True,
        "detail": "WinVaultKeyring",
    }
    assert not checks["word"]["required"] and not checks["word"]["ok"]


def test_frozen_workspace_inside_installation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "Ema"
    monkeypatch.setattr(install_check, "workspace_path", lambda: bundle / "workspace")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(bundle / "ema-cli.exe"))
    result = install_check.check_install()
    workspace = next(item for item in result["checks"] if item["name"] == "workspace")
    assert workspace["required"] and not workspace["ok"]


def test_cli_exit_code_follows_only_required_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    checks = [{"name": "word", "ok": False, "required": False, "detail": "missing"}]
    monkeypatch.setattr(
        cli, "run_install_check", lambda: {"version": "0.1.0", "frozen": False, "checks": checks}
    )
    passed = runner.invoke(_app, ["check-install"])
    assert passed.exit_code == 0
    assert json.loads(passed.stdout)["checks"] == checks
    checks.append({"name": "resources", "ok": False, "required": True, "detail": "missing"})
    failed = runner.invoke(_app, ["check-install"])
    assert failed.exit_code == 1
    assert json.loads(failed.stdout)["checks"] == checks
