from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PresentationBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class PresentationStatus(PresentationBaseModel):
    status: str = "available"
    status_label: str | None = None
    message: str | None = None


class MetricCard(PresentationBaseModel):
    label: str = ""
    value: Any = None
    raw_value: Any = None
    unit: str | None = None
    status: str = "available"
    status_label: str | None = None
    source: str | None = None
    note: str | None = None


class QuickOverviewPresentation(PresentationBaseModel):
    title: str | None = None
    status: str = "available"
    status_label: str | None = None
    cards: list[MetricCard] = Field(default_factory=list)
    summary_bar: dict[str, Any] = Field(default_factory=dict)


class MarketContextPresentation(PresentationBaseModel):
    cards: list[MetricCard] = Field(default_factory=list)
    health: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    narrative: str | None = None


class TableColumn(PresentationBaseModel):
    key: str = ""
    label: str = ""


class TableRow(PresentationBaseModel):
    pass


class FinancialTablePresentation(PresentationBaseModel):
    title: str | None = None
    status: str = "available"
    status_label: str | None = None
    columns: list[Any] = Field(default_factory=list)
    rows: list[Any] = Field(default_factory=list)
    source: str | None = None
    period_count: int | None = None
    missing_reason: str | None = None


class ActionTablePresentation(PresentationBaseModel):
    title: str | None = None
    status: str = "available"
    status_label: str | None = None
    rows: list[Any] = Field(default_factory=list)
    missing_reason: str | None = None


class ScenarioTablePresentation(PresentationBaseModel):
    title: str | None = None
    status: str = "available"
    status_label: str | None = None
    rows: list[Any] = Field(default_factory=list)
    missing_reason: str | None = None


class ChecklistPresentation(PresentationBaseModel):
    title: str | None = None
    status: str = "available"
    status_label: str | None = None
    items: list[Any] = Field(default_factory=list)
    missing_reason: str | None = None


class DataCoverageItem(PresentationBaseModel):
    key: str | None = None
    title: str | None = None
    label: str | None = None
    status: str = "available"
    status_label: str | None = None
    value: Any = None
    description: str | None = None
    note: str | None = None


class DataCoveragePresentation(PresentationBaseModel):
    title: str | None = None
    items: list[DataCoverageItem] = Field(default_factory=list)


class ReportPresentation(PresentationBaseModel):
    quick_overview: QuickOverviewPresentation = Field(default_factory=QuickOverviewPresentation)
    market_context_view: MarketContextPresentation = Field(default_factory=MarketContextPresentation)
    financial_table: FinancialTablePresentation = Field(default_factory=FinancialTablePresentation)
    action_table: ActionTablePresentation = Field(default_factory=ActionTablePresentation)
    scenario_table: ScenarioTablePresentation = Field(default_factory=ScenarioTablePresentation)
    checklist: ChecklistPresentation = Field(default_factory=ChecklistPresentation)
    data_coverage: DataCoveragePresentation = Field(default_factory=DataCoveragePresentation)
    summary_bar: dict[str, Any] = Field(default_factory=dict)
    coverage_rows: list[Any] = Field(default_factory=list)
    source_backed_enrichment: dict[str, Any] = Field(default_factory=dict)
