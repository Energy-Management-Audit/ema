"""HTTP adapters for client registry, uploads, and ANAF."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, File, UploadFile

from ema.api.models import (
    AnafState,
    Client,
    ClientFile,
    ClientIn,
    ClientPatch,
    Contact,
    EmptyInput,
    FileVersion,
    Site,
)
from ema.clients import anaf, files, registry
from ema.core.workspace import Workspace


def install_client_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/clients", tags=["clients"], response_model=list[Client])
    def clients() -> list[dict[str, object]]:
        return registry.list_clients(ws)

    @app.post("/clients", tags=["clients"], response_model=Client, status_code=201)
    def create_client(body: ClientIn) -> dict[str, object]:
        return registry.create_client(ws, body.name, body.cui)

    @app.get("/clients/{client_id}", tags=["clients"], response_model=Client)
    def client(client_id: str) -> dict[str, object]:
        return registry.get_client(ws, client_id)

    @app.patch("/clients/{client_id}", tags=["clients"], response_model=Client)
    def patch_client(client_id: str, body: ClientPatch) -> dict[str, object]:
        patch = body.model_dump(exclude_unset=True, exclude={"on_revision"})
        return registry.update_client(ws, client_id, patch, body.on_revision)

    @app.post(
        "/clients/{client_id}/files", tags=["clients"], response_model=ClientFile, status_code=201
    )
    def upload(client_id: str, file: Annotated[UploadFile, File()]) -> dict[str, object]:
        return files.store_upload(ws, client_id, file.file, file.filename or "")

    @app.get(
        "/clients/{client_id}/files/{file_sha}/versions",
        tags=["clients"],
        response_model=list[FileVersion],
    )
    def versions(client_id: str, file_sha: str) -> list[dict[str, object]]:
        return files.file_versions(ws, client_id, file_sha)

    @app.post("/clients/{client_id}/anaf/refresh", tags=["clients"], response_model=AnafState)
    def refresh(client_id: str, _body: EmptyInput) -> dict[str, object]:
        return anaf.refresh(ws, client_id)

    @app.get("/clients/{client_id}/sites", tags=["clients"], response_model=list[Site])
    def sites(client_id: str) -> list[dict[str, object]]:
        return registry.list_sites(ws, client_id)

    @app.get("/clients/{client_id}/contacts", tags=["clients"], response_model=list[Contact])
    def contacts(client_id: str) -> list[dict[str, object]]:
        return registry.list_contacts(ws, client_id)
