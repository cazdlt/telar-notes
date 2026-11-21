"""FastAPI application factory and security/size-limit middleware."""

from __future__ import annotations

import os
import pathlib
import time
import urllib.parse
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.exceptions import HTTPException as StarletteHTTPException

from telar.config import TelarConfig
from telar.deps import AppState, api_error
from telar.mcp_server import create_mcp_server
from telar.routes import files, links, search, settings, static, tasks
from telar.sections import SectionError
from telar.tasks import TaskLocationError

MAX_BODY_BYTES = 50 * 1024 * 1024
_DEFAULT_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})


def _parse_allowed_hosts(extra: Iterable[str] | None = None) -> frozenset[str]:
    """Return normalized Host/Origin hostnames including localhost defaults."""
    raw = (
        os.environ.get("TELAR_ALLOWED_HOSTS", "").split(",") if extra is None else extra
    )
    entries = {
        host for entry in raw if (host := entry.split(":", 1)[0].strip().lower())
    }
    return _DEFAULT_ALLOWED_HOSTS | entries


def create_app(
    vault_path: str,
    config: TelarConfig,
    session_path: str,
    activity: dict[str, float] | None = None,
    allowed_hosts: Iterable[str] | None = None,
) -> FastAPI:
    """Create and configure the Telar Notes FastAPI application."""
    allowed = _parse_allowed_hosts(allowed_hosts)
    tracker = activity if activity is not None else {"t": time.time()}
    state = AppState(
        fallback_vault=pathlib.Path(vault_path),
        config=config,
        session_path=session_path,
        activity=tracker,
    )
    mcp_server = create_mcp_server(state)
    # Telar's own boundary middleware enforces Host/Origin against TELAR_ALLOWED_HOSTS.
    mcp_subapp = mcp_server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.telar = state
    app.state.mcp = mcp_server

    @app.middleware("http")
    async def boundary_and_limits(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Allowed-hosts boundary: block cross-origin browser access and DNS-rebinding.
        host = (request.headers.get("host") or "").split(":")[0].strip().lower()
        if host not in allowed:
            return api_error(403, "forbidden")
        origin = request.headers.get("origin")
        if origin:
            origin_host = (urllib.parse.urlparse(origin).hostname or "").lower()
            if origin_host not in allowed:
                return api_error(403, "forbidden")

        if request.method == "OPTIONS":
            # No CORS: same-origin, localhost-only API.
            return Response(status_code=204)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    return api_error(413, "payload too large")
            except ValueError:
                return api_error(400, "invalid content-length")

        tracker["t"] = time.time()
        return await call_next(request)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> Response:
        message = "not found" if exc.status_code == 404 else str(exc.detail)
        return api_error(exc.status_code, message)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> Response:
        errors = exc.errors()
        if errors:
            first = errors[0]
            if first.get("loc") == ("query", "sort"):
                return api_error(400, "invalid sort")
            msg = str(first.get("msg", "invalid request"))
            if msg.startswith("Value error, "):
                msg = msg.removeprefix("Value error, ")
            return api_error(400, msg)
        return api_error(400, "invalid request")

    @app.exception_handler(SectionError)
    async def section_error_handler(_request: Request, exc: SectionError) -> Response:
        return api_error(exc.status, exc.message, **exc.extra)

    @app.exception_handler(TaskLocationError)
    async def task_location_error_handler(
        _request: Request, exc: TaskLocationError
    ) -> Response:
        return api_error(exc.status, str(exc))

    app.include_router(files.router)
    app.include_router(links.router)
    app.include_router(tasks.router)
    app.include_router(search.router)
    app.include_router(settings.router)
    app.include_router(static.router)
    app.router.routes.extend(mcp_subapp.routes)
    return app
