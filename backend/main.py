"""Local JARVIS HTTP API. Start from the repository root with python -m backend.main."""

import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from backend.config import Settings
from backend.core.assistant import Assistant

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["JARVIS"]
    ai_connected: bool


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.assistant = Assistant()
        yield

    application = FastAPI(
        title="JARVIS Local API",
        version="0.1.0",
        description="Local backend foundation. No AI model, voice, or computer control is connected.",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        responses={500: {"model": ErrorResponse, "description": "Unexpected server error"}},
    )
    application.state.settings = settings

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": f"http_{exc.status_code}", "message": str(exc.detail)}},
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "Invalid request data"}},
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unhandled API error", exc_info=(type(exc), exc, exc.__traceback__))
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error"}},
        )

    @application.get("/health", response_model=HealthResponse, tags=["System"],
                     summary="Check backend liveness")
    async def health(request: Request):
        return request.app.state.assistant.health()

    @application.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    async def documentation():
        # Self-contained documentation avoids third-party CDN requests.
        return """<!doctype html><html lang="en"><meta charset="utf-8">
<title>JARVIS API documentation</title><main><h1>JARVIS Local API v0.1.0</h1>
<p>No AI, voice, or computer control is connected.</p>
<h2>GET /health</h2><p>Backend liveness. Returns HTTP 200:</p>
<pre>{"status":"ok","service":"JARVIS","ai_connected":false}</pre>
<p><a href="/health">Open health check</a></p>
<h2>Errors</h2><p>HTTP errors use an error object containing code and message.
404: unknown route; 405: unsupported method; 422: invalid request;
500: unexpected server error. Internal exception details are not returned.</p>
<pre>{"error":{"code":"http_404","message":"Not Found"}}</pre>
<p><a href="/openapi.json">OpenAPI JSON schema</a></p></main></html>"""

    return application


app = create_app()


def main() -> None:
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port,
                log_level=settings.log_level, proxy_headers=False)


if __name__ == "__main__":
    main()
