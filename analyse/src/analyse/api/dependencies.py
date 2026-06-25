from __future__ import annotations

from analyse.clients.backend_client import BackendClient
from analyse.config.settings import Settings, get_settings
from analyse.repositories.ai_report_history_repository import AiReportHistoryRepository
from analyse.research.research_service import ExternalResearchService
from analyse.services.ai_report_history_service import AiReportHistoryService
from analyse.services.report_service import ReportService
from analyse.services.user_identity_service import UserIdentityService


def get_backend_client() -> BackendClient:
    return BackendClient(get_settings())


def get_external_research_service() -> ExternalResearchService:
    return ExternalResearchService(get_settings())


def get_user_identity_service() -> UserIdentityService:
    return UserIdentityService(get_backend_client())


def get_ai_report_history_repository() -> AiReportHistoryRepository:
    return AiReportHistoryRepository(get_settings())


def get_ai_report_history_service() -> AiReportHistoryService:
    settings: Settings = get_settings()
    return AiReportHistoryService(settings=settings, repository=get_ai_report_history_repository())


def get_report_service() -> ReportService:
    settings: Settings = get_settings()
    backend_client = get_backend_client()
    return ReportService(
        settings=settings,
        backend_client=backend_client,
        research_service=get_external_research_service(),
        user_identity_service=UserIdentityService(backend_client),
        history_service=get_ai_report_history_service(),
    )
