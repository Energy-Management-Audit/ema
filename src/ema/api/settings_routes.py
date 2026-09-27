"""Settings HTTP adapters without provider key persistence."""

from fastapi import FastAPI, HTTPException, Response

from ema.api.models import EmptyInput, ProviderKeyInput, ProviderTest, SettingsPatch, SettingsView
from ema.core import settings
from ema.core.errors import EmaError
from ema.core.workspace import Workspace


def install_settings_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/settings", tags=["settings"], response_model=SettingsView)
    def get_settings() -> dict[str, object]:
        return settings.read(ws)

    @app.put("/settings", tags=["settings"], response_model=SettingsView)
    def put_settings(body: SettingsPatch) -> dict[str, object]:
        extras = body.model_extra or {}
        if any("key" in key.lower() for key in extras):
            raise EmaError("key_not_allowed", "Cheile furnizorilor se setează în mediu.", "")
        if extras:
            raise HTTPException(422, "validation_error")
        patch = body.model_dump(exclude_unset=True)
        if patch.get("extraction") is None:
            patch.pop("extraction", None)
        return settings.update(ws, patch)

    @app.post("/settings/providers/{provider}/test", tags=["settings"], response_model=ProviderTest)
    def test_provider(provider: str, _body: EmptyInput) -> dict[str, object]:
        return settings.test_provider(ws, provider)

    @app.put("/settings/providers/{provider}/key", tags=["settings"], status_code=204)
    def put_provider_key(provider: str, body: ProviderKeyInput) -> Response:
        settings.set_provider_key(ws, provider, body.key)
        return Response(status_code=204)

    @app.delete("/settings/providers/{provider}/key", tags=["settings"], status_code=204)
    def delete_provider_key(provider: str) -> Response:
        settings.remove_provider_key(ws, provider)
        return Response(status_code=204)
