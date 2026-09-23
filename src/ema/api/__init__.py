"""Local-only API factory."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from ema import __version__
from ema.core.errors import EmaError
from ema.core.logging import write_event
from ema.core.workspace import Workspace


def create_app(workspace: Workspace, port: int) -> FastAPI:
    app = FastAPI()
    allowed = f"127.0.0.1:{port}"
    origin = f"http://{allowed}"

    @app.middleware("http")
    async def local_origin(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.headers.get("host") != allowed:
            return JSONResponse({"detail": "Invalid Host"}, status_code=421)
        if request.headers.get("origin") not in (None, origin):
            return JSONResponse({"detail": "Invalid Origin"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(EmaError)
    async def ema_error(_request: Request, exc: EmaError) -> JSONResponse:
        with workspace.app_log() as handle:
            write_event(handle, "interface_error", code=exc.code, detail=exc.detail)
        return JSONResponse(
            {"type": f"urn:ema:error:{exc.code}", "title": exc.user_message_ro, "status": 400},
            status_code=400,
            media_type="application/problem+json",
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "workspace": str(workspace.root)}

    return app
