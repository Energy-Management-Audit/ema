"""Reserved route installer for S17b home and settings."""

from fastapi import FastAPI

from ema.api.models import BackupResult, EmptyInput
from ema.core import backup
from ema.core.workspace import Workspace


def install_backup_routes(app: FastAPI, ws: Workspace) -> None:
    @app.post("/backups", tags=["settings"], status_code=201, response_model=BackupResult)
    def create_backup(_body: EmptyInput) -> backup.BackupResult:
        return backup.backup_now(ws)
