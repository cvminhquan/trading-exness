"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from exness_bot.api.dependencies import get_cached_settings, get_read_service
from exness_bot.api.errors import ApiAppError
from exness_bot.api.routes.v1 import router as v1_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    from exness_bot.candle_engine.runtime import (
        start_candle_engine_runtime,
        stop_candle_engine_runtime,
    )

    settings = get_cached_settings()
    if settings.paper_execution_enabled:
        from exness_bot.paper_execution.runtime import (
            start_paper_execution_runtime,
            stop_paper_execution_runtime,
        )

        start_paper_execution_runtime(settings, get_read_service())
        yield
        stop_paper_execution_runtime()
        return
    if settings.signal_engine_enabled:
        from exness_bot.signal_engine.runtime import (
            start_signal_engine_runtime,
            stop_signal_engine_runtime,
        )

        start_signal_engine_runtime(settings, get_read_service())
        yield
        stop_signal_engine_runtime()
        return
    if settings.candle_engine_enabled:
        start_candle_engine_runtime(settings, get_read_service())
    yield
    stop_candle_engine_runtime()


def create_app() -> FastAPI:
    settings = get_cached_settings()
    app = FastAPI(
        title="Exness Bot Read-only API",
        description=(
            "API phục vụ Dashboard. Chỉ đọc dữ liệu giao dịch. "
            "POST duy nhất được phép: chuyển tài khoản MT5 demo/thật (vẫn không đặt lệnh)."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "OPTIONS", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["Infrastructure"], summary="Health check")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(v1_router)

    @app.exception_handler(ApiAppError)
    async def handle_app_error(_request: Request, exc: ApiAppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    **({"details": exc.details} if exc.details is not None else {}),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_PARAMETER",
                    "message": "Tham số yêu cầu không hợp lệ.",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("api_internal_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Đã xảy ra lỗi nội bộ.",
                }
            },
        )

    return app


app = create_app()
