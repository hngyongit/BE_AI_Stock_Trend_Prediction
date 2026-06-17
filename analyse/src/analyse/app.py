from __future__ import annotations

from fastapi import FastAPI

from analyse.api.routes import router as analyse_router
from analyse.config.settings import get_settings
from analyse.utils.response_utils import success_response


def create_app() -> FastAPI:
    """Khoi tao FastAPI app doc lap cho analyse service."""
    settings = get_settings()
    app = FastAPI(
        title="Analyse Service",
        description="Skeleton Python cho tang phan tich chung khoan Viet Nam bang AI/LLM.",
        version="0.1.0",
        docs_url="/api/analyse/docs",
        redoc_url="/api/analyse/redoc",
    )

    @app.get("/")
    async def root() -> dict:
        return success_response(
            "Analyse service đã sẵn sàng. Logic phân tích AI/LLM sẽ được triển khai ở bước tiếp theo.",
            data={
                "service": "analyse",
                "port": settings.analyse_port,
                "baseRoute": "/api/analyse",
            },
        )

    app.include_router(analyse_router)
    return app
