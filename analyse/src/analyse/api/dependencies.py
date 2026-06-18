from __future__ import annotations

from analyse.clients.backend_client import BackendClient
from analyse.config.settings import Settings, get_settings
from analyse.research.research_service import ExternalResearchService
from analyse.services.report_service import ReportService


def get_backend_client() -> BackendClient:
    return BackendClient(get_settings())


def get_external_research_service() -> ExternalResearchService:
    return ExternalResearchService(get_settings())


def get_report_service() -> ReportService:
    settings: Settings = get_settings()
    return ReportService(settings=settings, backend_client=get_backend_client(), research_service=get_external_research_service())
