"""HTTP adapters for client registry, uploads, and ANAF."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel, ConfigDict

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
from ema.clients.overview import overview
from ema.clients.profile import profile
from ema.core.errors import EmaError
from ema.core.workspace import Workspace
from ema.energy_data.annex_index import AnnexImport, import_annexes


class CuiInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cui: str


class Consumption(BaseModel):
    year: int
    total_tep: str


class ClientOverview(BaseModel):
    id: str
    name: str | None
    cui: str | None
    county: str | None
    caen: str | None
    caen_description: str | None
    anaf_refreshed_at: str | None
    annex_years: list[int]
    consumption: Consumption | None
    pods: list[str]


class Identification(BaseModel):
    name: str | None
    cui: str | int | None
    registration: str | None
    address: str | None
    caen: str | int | None
    caen_description: str | None
    source: str
    retrieved_at: str | None
    annex_year: int | None


class ContactPerson(BaseModel):
    name: str
    source: str
    annex_year: int | None


class MemoryRow(BaseModel):
    kind: str
    identifier: str
    job_id: str
    confirmed_at: str
    active: bool


class AnnexRow(BaseModel):
    sha: str
    year: int
    file_name: str | None
    read_at: str


class ClientProfile(BaseModel):
    client: Client
    identification: Identification | None
    fiscal: dict[str, bool | None] | None
    energy_manager: Contact | None
    contact_person: ContactPerson | None
    memory: list[MemoryRow]
    annexes: list[AnnexRow]


def install_client_routes(app: FastAPI, ws: Workspace) -> None:  # noqa: C901
    @app.get("/clients", tags=["clients"], response_model=list[Client])
    def clients() -> list[dict[str, object]]:
        return registry.list_clients(ws)

    @app.post("/clients", tags=["clients"], response_model=Client, status_code=201)
    def create_client(body: ClientIn) -> dict[str, object]:
        return registry.create_client(ws, body.name, body.cui)

    @app.get("/clients/overview", tags=["clients"], response_model=list[ClientOverview])
    def clients_overview() -> list[dict[str, Any]]:
        return overview(ws)

    @app.post("/clients/annexes", tags=["clients"], response_model=AnnexImport)
    def annexes(files: Annotated[list[UploadFile], File()]) -> AnnexImport:
        if len(files) > 100:
            raise EmaError("file_too_large", "Sunt prea multe fişiere.", "")
        return import_annexes(ws, [(file.filename or "", file.file) for file in files])

    @app.post("/clients/from-anaf", tags=["clients"], response_model=Client, status_code=201)
    def from_anaf(body: CuiInput) -> dict[str, Any]:
        return anaf.create_from_anaf(ws, body.cui)

    @app.get("/clients/{client_id}", tags=["clients"], response_model=Client)
    def client(client_id: str) -> dict[str, object]:
        return registry.get_client(ws, client_id)

    @app.get("/clients/{client_id}/profile", tags=["clients"], response_model=ClientProfile)
    def client_profile(client_id: str) -> dict[str, Any]:
        return profile(ws, client_id)

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
