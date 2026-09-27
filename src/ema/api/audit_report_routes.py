"""Reserved route installer for S17b audit report."""

from fastapi import FastAPI

from ema.core.workspace import Workspace


def install_audit_report_routes(app: FastAPI, ws: Workspace) -> None:
    pass
