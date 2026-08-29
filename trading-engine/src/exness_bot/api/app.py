"""FastAPI application factory."""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from exness_bot.api.dependencies import get_cached_settings
from exness_bot.api.errors import ApiAppError
from exness_bot.api.routes.v1 import router as v1_router

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_cached_settings()
    app = FastAPI(
        title="Exness Bot Read-only API",
        description=(
            "API read-only phục vụ Dashboard. Không hỗ trợ đặt lệnh, sửa SL/TP, "
            "start/stop bot hoặc thay đổi cấu hình risk/strategy."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET"],
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
