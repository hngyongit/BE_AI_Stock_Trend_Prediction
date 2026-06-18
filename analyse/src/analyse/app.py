from __future__ import annotations

from fastapi import FastAPI

from analyse.api.routes import router
from analyse.config.settings import get_settings
from analyse.schemas.common import api_success


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

    app.include_router(router)
    return app
