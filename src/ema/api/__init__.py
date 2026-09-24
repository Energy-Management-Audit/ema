"""Local HTTP API and session boundary."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ema import __version__
from ema.api.models import Health, SessionResult
from ema.api.routes import install_routes
from ema.core.errors import EmaError
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
            return JSONResponse({"detail": "Invalid Host"}, status_code=421)
        origin = request.headers.get("origin")
        if origin is not None and origin != allowed_origin:
            return JSONResponse({"detail": "Invalid Origin"}, status_code=403)
        if request.url.path not in (
            "/",
            "/session",
            "/health",
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
        ) and not request.url.path.startswith("/assets/"):
            session = request.cookies.get("ema_session", "")
            if session not in sessions:
                return JSONResponse({"detail": "Session required"}, status_code=403)
            if (
                request.method not in ("GET", "HEAD", "OPTIONS")
                and request.headers.get("x-ema-csrf") != sessions[session]
            ):
                return JSONResponse({"detail": "CSRF token required"}, status_code=403)
        return await call_next(request)

    @app.post("/session", tags=["session"], response_model=SessionResult)
    async def create_session(body: SessionInput, response: Response) -> Response | dict[str, str]:
        nonlocal pending_code
        if not pending_code or not secrets.compare_digest(body.code, pending_code):
            return JSONResponse({"detail": "Invalid launch code"}, status_code=403)
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
        return JSONResponse(
            {"type": f"urn:ema:error:{exc.code}", "title": exc.user_message_ro, "status": 400},
            status_code=400,
            media_type="application/problem+json",
        )

    @app.get("/health", tags=["session"], response_model=Health)
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    frontend = resource_path("frontend")
    if (frontend / "index.html").exists():

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(frontend / "index.html")

        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    install_routes(app, workspace, mock=mock)
    return app
