"""Synthetic job fixture with an explicitly registered client."""

from ema.core.jobs import JobType
from ema.core.jobs import create_job as _create_job
from ema.core.workspace import Workspace


def register_client(ws: Workspace, client: str) -> None:
    with ws.connect() as db:
        db.execute("INSERT OR IGNORE INTO clients(id) VALUES (?)", (client,))


def create_job(ws: Workspace, type: JobType, client: str, year: int | None) -> str:
    if type != "reporting":
        register_client(ws, client)
    return _create_job(ws, type, client, year)
