"""Reserved route installer for S17b home and settings."""

from fastapi import FastAPI

from ema.core.workspace import Workspace


def install_backup_routes(app: FastAPI, ws: Workspace) -> None:
    pass
