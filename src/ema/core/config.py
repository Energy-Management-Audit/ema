"""Workspace discovery and local application settings."""

import os
import sys
import tomllib
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ema.core.errors import EmaError
from ema.core.resources import resource_path
from ema.core.workspace import Workspace


def workspace_path() -> Path:
    if location := os.environ.get("EMA_WORKSPACE"):
        return Path(location).expanduser().resolve()
    config = Path(user_config_dir("Ema")) / "config.toml"
    if config.exists():
        try:
            location = tomllib.loads(config.read_text(encoding="utf-8"))["workspace"]
            if not isinstance(location, str):
                raise TypeError("workspace must be a string")
            return Path(location).expanduser().resolve()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise EmaError(
                "config_invalid", "Configurația spațiului de lucru este invalidă.", str(exc)
            ) from exc
    if sys.platform == "darwin":
        return (Path.home() / "Ema").resolve()
    return Path(user_data_dir("Ema", roaming=True)).resolve()


def _word_default() -> Path:
    if sys.platform == "win32":
        return (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Microsoft Office/root/Office16/WINWORD.EXE"
        )
    return Path("/Applications/Microsoft Word.app")


def _tesseract_default() -> Path:
    if sys.platform == "win32":
        return resource_path("tesseract", "tesseract.exe")
    return Path("/opt/homebrew/bin/tesseract")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMA_", extra="ignore")
    word_path: Path = Field(default_factory=_word_default)
    word_timeout_s: float = Field(default=120, gt=0)
    tesseract_path: Path = Field(default_factory=_tesseract_default)
    provider: str | None = None
    model: str | None = None


def load_settings(workspace: Workspace) -> Settings:
    try:
        content = workspace.settings_text()
        if content is None:
            return Settings()
        values = tomllib.loads(content)
        return Settings.model_validate(values)
    except (OSError, ValueError) as exc:
        raise EmaError(
            "settings_invalid", "Setările spațiului de lucru sunt invalide.", str(exc)
        ) from exc
