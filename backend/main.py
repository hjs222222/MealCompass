"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.v1.health import router as health_router
from core.config import Settings, get_settings
from core.exceptions import AppError, ErrorResponse, request_id_context
from core.logging import configure_logging

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_MAX_LENGTH = 128
http_logger = logging.getLogger("mealcompass.http")


def _valid_request_id(value: str | None) -> bool:
    return bool(
        value
        and len(value) <= REQUEST_ID_MAX_LENGTH
        and value.isprintable()
        and not any(char.isspace() for char in value)
    )


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER)
    if not _valid_request_id(request_id):
        request_id = str(uuid4())
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    response: Response | None = None
    try:
        response = await call_next(request)
        return response
    except AppError as exc:
        response = _error_response(request, exc)
        return response
    except Exception as exc:
        http_logger.exception(
            "unhandled request exception",
            extra={"request_id": request_id, "exception_type": type(exc).__name__, "operation": "request"},
        )
        response = JSONResponse(
            status_code=500,
            content=ErrorResponse(
                code="internal_error",
                message="Internal server error",
                status=500,
                request_id=request_id,
            ).model_dump(),
        )
        return response
    finally:
        if response is not None:
            response.headers[REQUEST_ID_HEADER] = request_id
            http_logger.info(
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                },
            )
        request_id_context.reset(token)


def _request_id(request: Request) -> str:
    return request_id_context.get() or request.headers.get(REQUEST_ID_HEADER) or "unknown"


def _error_response(request: Request, error: AppError) -> JSONResponse:
    body = error.to_response(_request_id(request))
    return JSONResponse(status_code=body.status, content=body.model_dump())


def create_app(settings: Settings | None = None, *, include_test_routes: bool = False) -> FastAPI:
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        runtime_settings.validate_runtime()
        yield

    application = FastAPI(title="mealcompass-backend", version=runtime_settings.app_version, lifespan=lifespan)
    application.dependency_overrides = {}
    if settings is not None:
        from api.deps import get_app_settings

        application.dependency_overrides[get_app_settings] = lambda: settings

    @application.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(request, exc)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, _: RequestValidationError) -> JSONResponse:
        error = AppError("validation_error", "Request validation failed", 422)
        return _error_response(request, error)

    @application.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        http_logger.exception(
            "unhandled application exception",
            exc_info=exc,
            extra={"request_id": request_id, "exception_type": type(exc).__name__, "operation": "application"},
        )
        error = AppError("internal_error", "Internal server error", 500)
        return _error_response(request, error)

    application.middleware("http")(request_id_middleware)
    application.include_router(health_router)

    if include_test_routes:

        @application.get("/test-error")
        async def test_error(kind: str = "app") -> None:
            if kind == "generic":
                raise RuntimeError("test traceback must stay private")
            raise AppError("test_error", "test error", 400)

    return application


app = create_app(get_settings())
