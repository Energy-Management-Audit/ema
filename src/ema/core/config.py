"""Workspace discovery and local application settings."""

import os
import sys
import tomllib
from pathlib import Path
from typing import Any, ClassVar

import keyring
from keyring.errors import NoKeyringError
from platformdirs import user_config_dir, user_data_dir
from pydantic import Field, SecretStr, ValidationError
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from ema.core.errors import EmaError
from ema.core.resources import resource_path
from ema.core.workspace import Workspace


def workspace_path() -> Path:
    if location := os.environ.get("EMA_WORKSPACE"):
        return Path(location).expanduser().resolve()
    config = Path(user_config_dir("Ema", appauthor=False)) / "config.toml"
    if config.exists():
        try:
            location = tomllib.loads(config.read_text(encoding="utf-8"))["workspace"]
            if not isinstance(location, str):
                raise TypeError("workspace must be a string")
            return Path(location).expanduser().resolve()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise EmaError(
                "config_invalid", "Configuraţia spaţiului de lucru este invalidă.", str(exc)
            ) from exc
    if sys.platform == "darwin":
        return (Path.home() / "Ema").resolve()
    return Path(user_data_dir("Ema", appauthor=False, roaming=True)).resolve()


def _word_default() -> Path:
    if sys.platform == "win32":
        roots = (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")),
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")),
        )
        candidates = [
            root / "Microsoft Office" / office / "Office16" / "WINWORD.EXE"
            for office in ("root", "")
            for root in roots
        ]
        return next((path for path in candidates if path.is_file()), candidates[0])
    return Path("/Applications/Microsoft Word.app")


def _tesseract_default() -> Path:
    if sys.platform == "win32":
        return resource_path("tesseract", "tesseract.exe")
    return Path("/opt/homebrew/bin/tesseract")


class _ValuesSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings], values: dict[str, Any]) -> None:
        super().__init__(settings_cls)
        self._values = values

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        del field
        return self._values.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._values.copy()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMA_", env_ignore_empty=True, extra="ignore")
    _workspace_values: ClassVar[dict[str, Any]] = {}
    word_path: Path = Field(default_factory=_word_default)
    word_timeout_s: float = Field(default=120, gt=0)
    tesseract_path: Path = Field(default_factory=_tesseract_default)
    audit_base_document: Path | None = None
    audit_measurement_prototype: Path | None = None
    audit_measurement_sheet_model: Path | None = None
    piee_base_document: Path | None = None
    piee_base_directory: Path | None = None
    provider: str | None = None
    model: str | None = None
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    llm_live: bool = False

    def provider_key(self, provider: str) -> SecretStr | None:
        if provider not in {"gemini", "openai"}:
            raise ValueError(f"Unknown provider: {provider}")
        name = f"{provider}_api_key"
        if key := getattr(self, name):
            return key
        try:
            value = keyring.get_password("Ema", name)
        except NoKeyringError:
            return None
        except Exception as exc:
            raise EmaError(
                "keyring_unavailable",
                "Depozitul de chei al sistemului nu poate fi citit.",
                f"{type(exc).__name__}: {exc}",
            ) from exc
        return SecretStr(value) if value else None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del dotenv_settings, file_secret_settings
        workspace = {
            key: value
            for key, value in cls._workspace_values.items()
            if key not in {"gemini_api_key", "openai_api_key", "llm_live"}
        }
        return (
            env_settings,
            init_settings,
            _ValuesSource(settings_cls, workspace),
        )


def load_settings(
    workspace: Workspace, *, workspace_values: dict[str, Any] | None = None
) -> Settings:
    try:
        if workspace_values is None:
            content = workspace.settings_text()
            workspace_values = tomllib.loads(content) if content is not None else {}

        class WorkspaceSettings(Settings):
            _workspace_values: ClassVar[dict[str, Any]] = workspace_values

        try:
            return WorkspaceSettings()
        except ValidationError as exc:
            environment = EnvSettingsSource(WorkspaceSettings)()
            for error in exc.errors():
                field = error["loc"][0]
                if isinstance(field, str) and field in environment:
                    variable = f"EMA_{field.upper()}"
                    raise EmaError(
                        "settings_invalid",
                        f"Variabila de mediu {variable} este invalidă.",
                        f"{variable}: {exc}",
                    ) from exc
            raise
    except (OSError, ValueError) as exc:
        raise EmaError(
            "settings_invalid", "Setările spaţiului de lucru sunt invalide.", str(exc)
        ) from exc
