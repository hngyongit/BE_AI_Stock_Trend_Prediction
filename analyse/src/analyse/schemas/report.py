from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from analyse.schemas.common import ProviderName, SourceStatus
from analyse.schemas.stock import AnalysisOptions


class AnalyseOneReportRequest(BaseModel):
    provider: ProviderName | None = None
    model: str | None = None
    symbol: str
    scope_exchange: str = Field(default="HOSE", alias="scopeExchange")
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)

    model_config = ConfigDict(populate_by_name=True)


class ProviderMetadata(BaseModel):
    name: ProviderName
    model: str
    status: SourceStatus = "not_implemented"
    latency_ms: int = 0


class DataSourceStatus(BaseModel):
    name: str
    type: str
    status: SourceStatus
    detail: str | None = None


class MarkdownReport(BaseModel):
    available: bool = False
    output_path: str | None = None
    content: str | None = None


class HtmlReport(BaseModel):
    available: bool = False
    output_path: str | None = None
    content: str | None = None
    template_name: str | None = None


class ReportData(BaseModel):
    report_id: str
    generated_at: str
    symbol: str
    company: str | None = None
    scope_exchange: str = "HOSE"
    language: str = "vi"
    summary_schema_version: str = "1.0"
    provider: ProviderMetadata
    data_sources: list[DataSourceStatus] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    markdown_report: MarkdownReport = Field(default_factory=MarkdownReport)
    html_report: HtmlReport = Field(default_factory=HtmlReport)
    warnings: list[str] = Field(default_factory=list)


class ReportGenerateResponse(BaseModel):
    code: int = 200
    message: str = "Tạo dữ liệu report thành công"
    data: ReportData
