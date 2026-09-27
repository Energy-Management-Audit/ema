"""Local HTTP API and session boundary."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from ema import __version__
from ema.api.audit_forms import install_audit_forms
from ema.api.audit_routes import install_audit_routes
from ema.api.clients_routes import install_client_routes
from ema.api.errors import from_ema, install_error_contract, problem
from ema.api.evidence_routes import install_evidence_routes
from ema.api.invoice_routes import install_invoice_routes
from ema.api.job_routes import install_job_routes
from ema.api.models import Health, SessionResult
from ema.api.piee_routes import install_piee_routes
from ema.api.reporting_routes import install_reporting_routes
from ema.api.routes import install_routes
from ema.api.settings_routes import install_settings_routes
from ema.core.errors import EmaError
from ema.core.jobs import recover
from ema.core.logging import write_event
from ema.core.resources import resource_path
from ema.core.workspace import Workspace


class SessionInput(BaseModel):
    code: str


def create_app(  # noqa: C901
    workspace: Workspace,
    port: int,
    *,
    launch_code: str | None = None,
    dev_origin: str | None = None,
    mock: bool = False,
) -> FastAPI:
    """Create a loopback-only app; launch_code is delivered in a URL fragment."""
    recover(workspace)
    app = FastAPI(title="Ema local API", version=__version__, openapi_version="3.1.0")
    api_origin = f"http://127.0.0.1:{port}"
    allowed_origin = dev_origin if dev_origin is not None else api_origin
    pending_code = launch_code or secrets.token_urlsafe(32)
    sessions: dict[str, str] = {}

    @app.middleware("http")
    async def local_session(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.headers.get("host") != f"127.0.0.1:{port}":
            return problem("invalid_host", 421)
        origin = request.headers.get("origin")
        if origin is not None and origin != allowed_origin:
            return problem("invalid_origin", 403)
        if request.url.path not in (
            "/",
            "/session",
            "/health",
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/app",
        ) and not request.url.path.startswith(("/assets/", "/app/")):
            session = request.cookies.get("ema_session", "")
            if session not in sessions:
                return problem("session_required", 403)
            if (
                request.method not in ("GET", "HEAD", "OPTIONS")
                and request.headers.get("x-ema-csrf") != sessions[session]
            ):
                return problem("csrf_required", 403)
            request.state.human_session = True
        return await call_next(request)

    @app.post("/session", tags=["session"], response_model=SessionResult)
    async def create_session(body: SessionInput, response: Response) -> Response | dict[str, str]:
        nonlocal pending_code
        if not pending_code or not secrets.compare_digest(body.code, pending_code):
            return problem("session_required", 403)
        pending_code = ""
        session = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        sessions[session] = csrf
        response.set_cookie("ema_session", session, httponly=True, samesite="strict", path="/")
        return {"csrf": csrf}

    @app.exception_handler(EmaError)
    async def ema_error(_request: Request, exc: EmaError) -> JSONResponse:
        with workspace.app_log() as handle:
            write_event(handle, "interface_error", code=exc.code)
        return from_ema(exc)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        code = (
            exc.detail
            if exc.detail in ("human_required", "provisional_contract", "audit_render_unavailable")
            else "validation_error"
            if exc.status_code == 422
            else "not_found"
            if exc.status_code == 404
            else "invalid_id"
        )
        return problem(code, exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def starlette_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem("not_found" if exc.status_code == 404 else "request_error", exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return problem("validation_error", 422)

    @app.get("/health", tags=["session"], response_model=Health)
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    frontend = resource_path("frontend")
    if (frontend / "index.html").exists():

        @app.get("/", include_in_schema=False)
        @app.get("/app", include_in_schema=False)
        @app.get("/app/{path:path}", include_in_schema=False)
        def index() -> FileResponse:
            # A static shell holding no data, so deep links reload without a session.
            return FileResponse(frontend / "index.html")

        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    install_routes(app, workspace, mock=mock)
    install_audit_routes(app, workspace)
    install_audit_forms(app, workspace)
    install_client_routes(app, workspace)
    install_evidence_routes(app, workspace, mock=mock)
    install_job_routes(app, workspace)
    install_invoice_routes(app, workspace)
    install_piee_routes(app, workspace)
    install_reporting_routes(app, workspace)
    install_settings_routes(app, workspace)
    install_error_contract(app)
    return app
