from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analyse.api.routes import router
from analyse.config.settings import get_settings
from analyse.schemas.common import api_success
from analyse.services.config_diagnostic_service import log_startup_config


def create_app() -> FastAPI:
    """Khởi tạo FastAPI app độc lập cho analyse service."""
    settings = get_settings()
    app = FastAPI(
        title="Analyse Service",
        description="Service Python/FastAPI phân tích cổ phiếu Việt Nam bằng AI/LLM, hỗ trợ Gemini và OpenAI.",
        version="0.2.0",
        docs_url="/api/analyse/docs",
        redoc_url="/api/analyse/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origin_list,
        allow_credentials=settings.effective_cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root() -> dict:
        return api_success(
            "Analyse service đã sẵn sàng.",
            data={
                "service": "analyse",
                "port": settings.analyse_port,
                "docs": "/api/analyse/docs",
                "target_endpoint": "/api/ai-reports/analyse-one",
            },
        )

    @app.on_event("startup")
    async def startup_config_log() -> None:
        log_startup_config(settings)

    app.include_router(router)
    return app
