from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ColumnType = Literal["string", "number", "integer", "boolean", "date", "datetime", "object"]
WarningSeverity = Literal["info", "warning", "error"]


class VisualizationWarning(BaseModel):
    code: str
    message: str
    severity: WarningSeverity = "warning"
    field: str | None = None


class VisualizationColumn(BaseModel):
    name: str
    type: ColumnType = "string"
    label: str | None = None
    unit: str | None = None
    derived: bool = False
    formula: str | None = None
    required_history_points: int | None = None
    source: str | None = None
    description: str | None = None


class VisualizationTable(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    columns: list[VisualizationColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    source: str | None = None


class VisualizationDataQuality(BaseModel):
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_statuses: list[dict[str, Any]] = Field(default_factory=list)
    derived_field_notes: list[str] = Field(default_factory=list)
    units: dict[str, Any] = Field(default_factory=dict)


class VisualizationDatasetMeta(BaseModel):
    source_report_id: str | None = None
    generated_from: str = "analyse_report"
    provider: dict[str, Any] = Field(default_factory=dict)
    data_sources: list[dict[str, Any]] = Field(default_factory=list)
    units: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    derived_field_notes: list[str] = Field(default_factory=list)
    row_limit: int | None = None
    chart_range: str | None = None
    data_quality: VisualizationDataQuality = Field(default_factory=VisualizationDataQuality)


class VisualizationOptions(BaseModel):
    chart_range: str | None = Field(default=None, alias="chartRange")
    include_csv_links: bool = Field(default=False, alias="includeCsvLinks")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class VisualizationDatasetData(BaseModel):
    schema_version: str
    symbol: str
    exchange: str
    generated_at: str
    meta: VisualizationDatasetMeta = Field(default_factory=VisualizationDatasetMeta)
    tables: list[VisualizationTable] = Field(default_factory=list)
    visualization: dict[str, Any] = Field(default_factory=dict)


class VisualizationDatasetResponse(BaseModel):
    code: int = 200
    message: str = "Visualization dataset generated successfully."
    data: VisualizationDatasetData
