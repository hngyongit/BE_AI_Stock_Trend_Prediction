from __future__ import annotations

import csv
import io
import json
import logging
import time
import math
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from statistics import pstdev
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

from analyse.config.settings import Settings, get_settings
from analyse.schemas.visualization import (
    VisualizationColumn,
    VisualizationDataQuality,
    VisualizationDatasetData,
    VisualizationDatasetMeta,
    VisualizationTable,
)
from analyse.services.presentation_contract import sanitize_data_source_statuses
from analyse.utils.debug_scrub import scrub_debug_payload, scrub_debug_text
from analyse.utils.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)


class VisualizationDatasetService:
    """Build chart-ready datasets from an already validated analyse report."""

    _cache_lock: RLock = RLock()
    _shared_signed_dataset_cache: dict[str, dict[str, Any]] = {}
    _shared_dataset_cache: dict[str, dict[str, Any]] = {}

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def build_from_report_response(
        self,
        report_response: dict[str, Any],
        *,
        chart_range: str | None = None,
    ) -> VisualizationDatasetData:
        data = self._dict(report_response.get("data"))
        summary = self._dict(data.get("summary"))
        derived_notes: list[str] = []
        warnings = self._string_list(data.get("warnings"))

        tables = [
            self.build_prices_table(summary, derived_notes),
            self.build_financial_periods_table(summary, derived_notes),
            self.build_scores_table(summary),
            self.build_peers_table(summary),
            self.build_market_context_table(summary),
            self.build_ai_signals_table(summary),
            self.build_data_quality_table(data, summary, derived_notes),
        ]

        symbol = normalize_symbol(data.get("symbol") or summary.get("symbol")) or "UNKNOWN"
        exchange = str(data.get("scope_exchange") or data.get("exchange") or summary.get("exchange") or "HOSE").strip().upper()
        data_quality = self._dict(summary.get("data_quality"))
        coverage = self._dict(summary.get("data_coverage"))
        missing_fields = self._dedupe_strings(
            [
                *self._string_list(data_quality.get("missing_fields") or data_quality.get("missingFields")),
                *self._missing_from_coverage(coverage),
            ]
        )
        data_sources = sanitize_data_source_statuses(self._list(data.get("data_sources")))
        units = self._dict(data_quality.get("units"))
        if not units:
            units = self._dict(self._dict(summary.get("bctc_3q")).get("units"))

        meta = VisualizationDatasetMeta(
            source_report_id=self._optional_text(data.get("report_id")),
            provider=self._dict(data.get("provider")),
            data_sources=data_sources,
            units=units,
            warnings=self._dedupe_strings([*warnings, *self._string_list(data_quality.get("warnings"))]),
            missing_fields=missing_fields,
            derived_field_notes=self._dedupe_strings(derived_notes),
            row_limit=self.settings.visualization_max_rows,
            chart_range=chart_range or self.settings.visualization_default_chart_range,
            data_quality=VisualizationDataQuality(
                missing_fields=missing_fields,
                warnings=self._dedupe_strings([*warnings, *self._string_list(data_quality.get("warnings"))]),
                source_statuses=data_sources,
                derived_field_notes=self._dedupe_strings(derived_notes),
                units=units,
            ),
        )
        payload = VisualizationDatasetData(
            schema_version=self.settings.visualization_schema_version,
            symbol=symbol,
            exchange=exchange,
            generated_at=self._generated_at(data.get("generated_at")),
            meta=meta,
            tables=tables,
            visualization=self.build_chart_visualization(
                report_id=self._optional_text(data.get("report_id")),
                symbol=symbol,
                exchange=exchange,
                generated_at=self._generated_at(data.get("generated_at")),
                tables=tables,
                missing_fields=missing_fields,
            ),
        )
        clean_payload = self._scrub_visualization_payload(scrub_debug_payload(payload.model_dump(mode="json")))
        return VisualizationDatasetData.model_validate(clean_payload)

    def build_chart_visualization(
        self,
        *,
        report_id: str | None,
        symbol: str,
        exchange: str,
        generated_at: str,
        tables: list[VisualizationTable],
        missing_fields: list[str],
    ) -> dict[str, Any]:
        """Build compact chart-first ECharts options for the visualization tab."""
        table_map = {table.name: table for table in tables}
        charts: list[dict[str, Any]] = []
        omitted_charts: list[dict[str, str]] = []

        prices = self._table_rows(table_map, "prices")
        financials = self._table_rows(table_map, "financial_periods")[-12:]
        scores = self._table_rows(table_map, "scores")
        peers = self._table_rows(table_map, "peers")
        market = self._table_rows(table_map, "market_context")

        self._append_chart_safely(charts, omitted_charts, "price_volume", "Giá & khối lượng", lambda: self._price_volume_chart(prices), rows=len(prices))
        self._extend_charts_safely(charts, omitted_charts, "technical_indicators", "Chỉ báo kỹ thuật", lambda: self._technical_charts(prices), rows=len(prices))
        self._append_chart_safely(charts, omitted_charts, "financial_periods", "Kết quả kinh doanh", lambda: self._financial_chart(financials), rows=len(financials))
        self._append_chart_safely(charts, omitted_charts, "profitability_leverage", "ROE, ROA & đòn bẩy", lambda: self._profitability_chart(financials), rows=len(financials))
        self._append_chart_safely(charts, omitted_charts, "scores", "Điểm định lượng", lambda: self._scores_chart(scores), rows=len(scores), optional_reason="Không đủ điểm định lượng có ý nghĩa.")
        self._append_chart_safely(
            charts,
            omitted_charts,
            "peer_comparison",
            "So sánh cùng ngành",
            lambda: self._peer_chart(peers),
            rows=len(peers),
            optional_reason="Không đủ dữ liệu peer do Vietstock peer crawl lỗi hoặc thiếu dữ liệu.",
        )
        self._append_chart_safely(
            charts,
            omitted_charts,
            "market_context",
            "Bối cảnh thị trường",
            lambda: self._market_chart(market),
            rows=len(market),
            optional_reason="Không đủ dữ liệu market context.",
        )

        final_charts = [chart for chart in charts if chart]
        return {
            "schema_version": "visualization.v2",
            "report_id": report_id,
            "symbol": symbol,
            "exchange": exchange,
            "generated_at": generated_at,
            "charts": final_charts,
            "meta": {
                "chart_count": len(final_charts),
                "omitted_charts": omitted_charts,
                "has_missing_data": bool(missing_fields),
                "empty_chart_count": len([chart for chart in final_charts if chart.get("type") == "empty"]),
            },
        }

    def _append_chart_safely(
        self,
        charts: list[dict[str, Any]],
        omitted_charts: list[dict[str, str]],
        chart_id: str,
        title: str,
        builder: Any,
        *,
        rows: int,
        optional_reason: str | None = None,
    ) -> None:
        started = time.perf_counter()
        try:
            chart = builder()
        except Exception as exc:
            logger.warning("[visualization-data] omit_chart id=%s reason=builder_error rows=%s", chart_id, rows, exc_info=True)
            omitted_charts.append({"id": chart_id, "reason": f"Không thể tạo biểu đồ {title}: {exc.__class__.__name__}."})
            return
        duration_ms = int((time.perf_counter() - started) * 1000)
        if chart:
            charts.append(chart)
            logger.info("[visualization-data] build_chart id=%s rows=%s duration_ms=%s", chart.get("id", chart_id), rows, duration_ms)
            return
        reason = optional_reason or f"Không đủ dữ liệu để tạo biểu đồ {title}."
        logger.info("[visualization-data] omit_chart id=%s reason=no_valid_data rows=%s duration_ms=%s", chart_id, rows, duration_ms)
        omitted_charts.append({"id": chart_id, "reason": reason})

    def _extend_charts_safely(
        self,
        charts: list[dict[str, Any]],
        omitted_charts: list[dict[str, str]],
        chart_id: str,
        title: str,
        builder: Any,
        *,
        rows: int,
    ) -> None:
        started = time.perf_counter()
        try:
            built = [chart for chart in builder() if chart]
        except Exception as exc:
            logger.warning("[visualization-data] omit_chart id=%s reason=builder_error rows=%s", chart_id, rows, exc_info=True)
            omitted_charts.append({"id": chart_id, "reason": f"Không thể tạo biểu đồ {title}: {exc.__class__.__name__}."})
            return
        duration_ms = int((time.perf_counter() - started) * 1000)
        if built:
            charts.extend(built)
            logger.info("[visualization-data] build_chart id=%s count=%s rows=%s duration_ms=%s", chart_id, len(built), rows, duration_ms)
            return
        logger.info("[visualization-data] omit_chart id=%s reason=no_valid_data rows=%s duration_ms=%s", chart_id, rows, duration_ms)
        omitted_charts.append({"id": chart_id, "reason": f"Không đủ dữ liệu để tạo biểu đồ {title}."})

    def store_dataset_cache(self, dataset: VisualizationDatasetData, *, chart_range: str | None = None) -> list[str]:
        """Cache a visualization dataset for fast CSV/package exports."""
        now_ts = int(time.time())
        expires_at = now_ts + max(60, int(self.settings.visualization_dataset_ttl_seconds))
        keys = self._dataset_cache_keys(dataset, chart_range=chart_range)
        entry = {
            "dataset": dataset,
            "symbol": dataset.symbol,
            "exchange": dataset.exchange,
            "source_report_id": dataset.meta.source_report_id,
            "chart_range": chart_range or dataset.meta.chart_range or self.settings.visualization_default_chart_range,
            "created_at": now_ts,
            "expires_at": expires_at,
        }
        with self._cache_lock:
            self._cleanup_dataset_cache_locked(now_ts)
            for key in keys:
                self._shared_dataset_cache[key] = entry
        return keys

    def get_cached_dataset(
        self,
        *,
        symbol: str | None = None,
        exchange: str | None = None,
        chart_range: str | None = None,
        report_id: str | None = None,
    ) -> VisualizationDatasetData | None:
        keys = self._lookup_dataset_cache_keys(symbol=symbol, exchange=exchange, chart_range=chart_range, report_id=report_id)
        now_ts = int(time.time())
        with self._cache_lock:
            self._cleanup_dataset_cache_locked(now_ts)
            for key in keys:
                entry = self._shared_dataset_cache.get(key)
                if not entry:
                    continue
                dataset = entry.get("dataset")
                if isinstance(dataset, VisualizationDatasetData):
                    return dataset
        return None

    def export_csv_file(self, dataset: VisualizationDatasetData, table_name: str) -> Path:
        table = next((item for item in dataset.tables if item.name == table_name), None)
        if table is None:
            raise ValueError(f"Unknown visualization table: {table_name}")
        path = self._export_path(dataset, table_name, "csv")
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        csv_text = self.table_to_csv(dataset, table_name)
        path.write_text(csv_text, encoding="utf-8", newline="")
        return path

    def export_visualization_json_file(self, dataset: VisualizationDatasetData) -> Path:
        path = self._export_path(dataset, "visualization_v2", "json")
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_visualization_json_file(self, report_id: str | None) -> VisualizationDatasetData | None:
        clean_report_id = self._safe_part(report_id)
        if not clean_report_id:
            return None
        path = self._export_dir() / f"{clean_report_id}_visualization_v2.json"
        if not path.exists() or not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return VisualizationDatasetData.model_validate(payload)
        except Exception:
            return None

    def build_data_formulator_package(self, dataset: VisualizationDatasetData) -> dict[str, Any]:
        tables = []
        for table in dataset.tables:
            if table.name not in {"prices", "financial_periods"}:
                continue
            tables.append(
                {
                    "name": table.name,
                    "filename": self.export_csv_file(dataset, table.name).name,
                    "columns": [column.model_dump(mode="json") for column in table.columns],
                    "rows": table.rows,
                }
            )
        return {
            "schema_version": "data_formulator.v1",
            "report_id": dataset.meta.source_report_id,
            "symbol": dataset.symbol,
            "exchange": dataset.exchange,
            "tables": tables,
            "recommended_start_table": "prices",
            "notes": ["Use prices.csv first for price/candlestick/volume charts."],
        }

    def export_data_formulator_package_file(self, dataset: VisualizationDatasetData) -> Path:
        path = self._export_path(dataset, "data_formulator_package", "json")
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.build_data_formulator_package(dataset), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    def build_prices_table(self, summary: dict[str, Any], derived_notes: list[str]) -> VisualizationTable:
        rows = self._sort_price_rows(self._list(summary.get("price_history")))
        closes = [self._number(row.get("close"), row.get("close_price"), row.get("last_price")) for row in rows]
        volumes = [self._number(row.get("volume")) for row in rows]
        returns = self._daily_returns(closes)
        ma20 = self._rolling_mean(closes, 20)
        ma50 = self._rolling_mean(closes, 50)
        volume_ma20 = self._rolling_mean(volumes, 20)
        volatility_20d = self._rolling_volatility(returns, 20)
        drawdown_pct = self._drawdown_series(closes)
        rsi_14 = self._rsi_series(closes, 14) if len([v for v in closes if v is not None]) >= 15 else None
        macd_payload = self._macd_payload(closes) if len([v for v in closes if v is not None]) >= 35 else None

        table_rows: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            item = {
                "date": self._date_value(row),
                "open": self._number(row.get("open"), row.get("open_price")),
                "high": self._number(row.get("high"), row.get("high_price")),
                "low": self._number(row.get("low"), row.get("low_price")),
                "close": closes[idx],
                "volume": volumes[idx],
                "return_pct": returns[idx],
                "ma20": ma20[idx],
                "ma50": ma50[idx],
                "volume_ma20": volume_ma20[idx],
                "volatility_20d": volatility_20d[idx],
                "drawdown_pct": drawdown_pct[idx],
            }
            if rsi_14 is not None:
                item["rsi_14"] = rsi_14[idx]
            if macd_payload is not None:
                item["macd"] = macd_payload["macd"][idx]
                item["macd_signal"] = macd_payload["signal"][idx]
                item["macd_histogram"] = macd_payload["histogram"][idx]
            table_rows.append(item)

        columns = [
            VisualizationColumn(name="date", type="date", label="Ngày"),
            VisualizationColumn(name="open", type="number", label="Giá mở cửa", unit="VND"),
            VisualizationColumn(name="high", type="number", label="Giá cao nhất", unit="VND"),
            VisualizationColumn(name="low", type="number", label="Giá thấp nhất", unit="VND"),
            VisualizationColumn(name="close", type="number", label="Giá đóng cửa", unit="VND"),
            VisualizationColumn(name="volume", type="number", label="Khối lượng", unit="shares"),
            VisualizationColumn(
                name="return_pct",
                type="number",
                label="Biến động ngày",
                unit="%",
                derived=True,
                formula="(close / previous_close - 1) * 100",
                required_history_points=2,
            ),
            VisualizationColumn(
                name="ma20",
                type="number",
                label="MA20",
                derived=True,
                formula="rolling_mean(close, 20)",
                required_history_points=20,
            ),
            VisualizationColumn(
                name="ma50",
                type="number",
                label="MA50",
                derived=True,
                formula="rolling_mean(close, 50)",
                required_history_points=50,
            ),
            VisualizationColumn(
                name="volume_ma20",
                type="number",
                label="Volume MA20",
                derived=True,
                formula="rolling_mean(volume, 20)",
                required_history_points=20,
            ),
            VisualizationColumn(
                name="volatility_20d",
                type="number",
                label="Volatility 20 phiên",
                unit="%",
                derived=True,
                formula="population_std(return_pct, 20)",
                required_history_points=21,
            ),
            VisualizationColumn(
                name="drawdown_pct",
                type="number",
                label="Drawdown từ đỉnh gần nhất",
                unit="%",
                derived=True,
                formula="(close / running_max(close) - 1) * 100",
                required_history_points=2,
            ),
        ]
        derived_notes.extend(
            [
                "prices.return_pct derived from close and previous close.",
                "prices.ma20, prices.ma50 and prices.volume_ma20 use rolling means.",
                "prices.volatility_20d uses rolling population standard deviation of daily returns.",
                "prices.drawdown_pct is derived from running close-price peak.",
            ]
        )
        if rsi_14 is not None:
            columns.append(
                VisualizationColumn(
                    name="rsi_14",
                    type="number",
                    label="RSI 14",
                    derived=True,
                    formula="RSI(close, 14)",
                    required_history_points=15,
                )
            )
            derived_notes.append("prices.rsi_14 is derived from close-price changes over 14 periods.")
        if macd_payload is not None:
            columns.extend(
                [
                    VisualizationColumn(name="macd", type="number", label="MACD", derived=True, formula="EMA(close, 12) - EMA(close, 26)", required_history_points=26),
                    VisualizationColumn(name="macd_signal", type="number", label="MACD signal", derived=True, formula="EMA(macd, 9)", required_history_points=35),
                    VisualizationColumn(name="macd_histogram", type="number", label="MACD histogram", derived=True, formula="macd - macd_signal", required_history_points=35),
                ]
            )
            derived_notes.append("prices.macd, prices.macd_signal and prices.macd_histogram are derived from close-price EMA series.")

        return self._table(
            name="prices",
            title="OHLCV và chỉ báo kỹ thuật dẫn xuất",
            columns=columns,
            rows=table_rows,
            source="summary.price_history",
        )

    def build_financial_periods_table(self, summary: dict[str, Any], derived_notes: list[str]) -> VisualizationTable:
        financials = self._dict(summary.get("financials_merged")) or self._dict(summary.get("bctc_3q"))
        periods = self._list(financials.get("periods"))
        rows: list[dict[str, Any]] = []
        for period in self._sort_financial_periods(periods):
            liabilities = self._number(period.get("total_liabilities"), period.get("liabilities"))
            equity = self._number(period.get("equity"))
            debt_to_equity = self._number(period.get("debt_to_equity"))
            if debt_to_equity is None and liabilities is not None and equity not in (None, 0):
                debt_to_equity = self._round(liabilities / equity, 4)
            rows.append(
                {
                    "period": self._optional_text(period.get("period")),
                    "year": self._int(period.get("year")),
                    "quarter": self._int(period.get("quarter")),
                    "revenue": self._number(period.get("revenue")),
                    "gross_profit": self._number(period.get("gross_profit")),
                    "profit_after_tax": self._number(period.get("profit_after_tax")),
                    "parent_profit": self._number(period.get("parent_profit")),
                    "eps": self._number(period.get("eps")),
                    "roe": self._number(period.get("roe")),
                    "roa": self._number(period.get("roa"), period.get("roaa")),
                    "total_assets": self._number(period.get("total_assets")),
                    "total_liabilities": liabilities,
                    "equity": equity,
                    "debt_to_equity": debt_to_equity,
                }
            )
        derived_notes.append("financial_periods.debt_to_equity is derived from total_liabilities / equity when source value is missing.")
        return self._table(
            name="financial_periods",
            title="Các kỳ BCTC đã chuẩn hóa",
            columns=[
                VisualizationColumn(name="period", type="string", label="Kỳ"),
                VisualizationColumn(name="year", type="integer", label="Năm"),
                VisualizationColumn(name="quarter", type="integer", label="Quý"),
                VisualizationColumn(name="revenue", type="number", label="Doanh thu"),
                VisualizationColumn(name="gross_profit", type="number", label="Lợi nhuận gộp"),
                VisualizationColumn(name="profit_after_tax", type="number", label="LNST"),
                VisualizationColumn(name="parent_profit", type="number", label="LNST cổ đông công ty mẹ"),
                VisualizationColumn(name="eps", type="number", label="EPS"),
                VisualizationColumn(name="roe", type="number", label="ROE", unit="%"),
                VisualizationColumn(name="roa", type="number", label="ROA", unit="%"),
                VisualizationColumn(name="total_assets", type="number", label="Tổng tài sản"),
                VisualizationColumn(name="total_liabilities", type="number", label="Nợ phải trả"),
                VisualizationColumn(name="equity", type="number", label="Vốn chủ sở hữu"),
                VisualizationColumn(
                    name="debt_to_equity",
                    type="number",
                    label="Nợ/Vốn chủ",
                    derived=True,
                    formula="total_liabilities / equity when source debt_to_equity is missing",
                ),
            ],
            rows=rows,
            source="summary.financials_merged.periods|summary.bctc_3q.periods",
        )

    def build_scores_table(self, summary: dict[str, Any]) -> VisualizationTable:
        scores = self._dict(summary.get("scores"))
        explanations = self._dict(summary.get("score_explanations"))
        confidence = self._normalize_confidence(scores.get("score_confidence_normalized") or scores.get("score_confidence"))
        definitions = [
            ("overall", "overall_score", "Điểm tổng"),
            ("valuation", "valuation_score", "Định giá"),
            ("quality", "quality_score", "Chất lượng"),
            ("growth", "growth_score", "Tăng trưởng"),
            ("momentum", "momentum_score", "Động lượng"),
            ("liquidity", "liquidity_score", "Thanh khoản"),
            ("size", "size_score", "Quy mô"),
            ("risk", "risk_score", "Rủi ro"),
            ("data_confidence", "score_confidence_normalized", "Độ tin cậy dữ liệu"),
        ]
        rows = []
        for category, key, label in definitions:
            value = self._number(scores.get(key))
            if value is None and key == "score_confidence_normalized":
                value = confidence
            if value is None:
                continue
            rows.append(
                {
                    "category": category,
                    "label": label,
                    "score_value": value,
                    "confidence": confidence,
                    "reason": self._reason_text(explanations.get(key) or explanations.get(category)),
                }
            )
        return self._table(
            name="scores",
            title="Điểm định lượng",
            columns=[
                VisualizationColumn(name="category", type="string", label="Nhóm điểm"),
                VisualizationColumn(name="label", type="string", label="Tên hiển thị"),
                VisualizationColumn(name="score_value", type="number", label="Điểm"),
                VisualizationColumn(name="confidence", type="number", label="Độ tin cậy", unit="%"),
                VisualizationColumn(name="reason", type="string", label="Giải thích"),
            ],
            rows=rows,
            source="summary.scores",
        )

    def build_peers_table(self, summary: dict[str, Any]) -> VisualizationTable:
        peer_context = self._dict(summary.get("industry_peer_context"))
        industry = self._dict(peer_context.get("industry"))
        rows = []
        for peer in self._list(peer_context.get("peers")):
            rows.append(
                {
                    "peer_symbol": normalize_symbol(peer.get("symbol") or peer.get("ticker")),
                    "company": self._optional_text(peer.get("company") or peer.get("name")),
                    "exchange": self._optional_text(peer.get("exchange") or peer.get("market_code")),
                    "sector": self._optional_text(peer.get("sector") or industry.get("sector")),
                    "industry": self._optional_text(peer.get("industry") or industry.get("industry")),
                    "market_cap": self._number(peer.get("market_cap"), peer.get("market_cap_billion")),
                    "pe": self._number(peer.get("pe"), peer.get("pe_basic")),
                    "pb": self._number(peer.get("pb")),
                    "roe": self._number(peer.get("roe")),
                    "revenue": self._number(peer.get("revenue")),
                    "profit_after_tax": self._number(peer.get("profit_after_tax"), peer.get("parent_profit")),
                    "momentum_1m": self._number(peer.get("momentum_1m")),
                    "close_price": self._number(peer.get("close_price"), peer.get("price")),
                }
            )
        return self._table(
            name="peers",
            title="So sánh peer cùng ngành",
            columns=[
                VisualizationColumn(name="peer_symbol", type="string", label="Mã peer"),
                VisualizationColumn(name="company", type="string", label="Doanh nghiệp"),
                VisualizationColumn(name="exchange", type="string", label="Sàn"),
                VisualizationColumn(name="sector", type="string", label="Ngành cấp cao"),
                VisualizationColumn(name="industry", type="string", label="Ngành"),
                VisualizationColumn(name="market_cap", type="number", label="Vốn hóa"),
                VisualizationColumn(name="pe", type="number", label="P/E"),
                VisualizationColumn(name="pb", type="number", label="P/B"),
                VisualizationColumn(name="roe", type="number", label="ROE", unit="%"),
                VisualizationColumn(name="revenue", type="number", label="Doanh thu"),
                VisualizationColumn(name="profit_after_tax", type="number", label="LNST"),
                VisualizationColumn(name="momentum_1m", type="number", label="Momentum 1M", unit="%"),
                VisualizationColumn(name="close_price", type="number", label="Giá đóng cửa"),
            ],
            rows=rows,
            source="summary.industry_peer_context.peers",
        )

    def build_market_context_table(self, summary: dict[str, Any]) -> VisualizationTable:
        market = self._dict(summary.get("hose_market_context")) or self._dict(summary.get("market_general_context"))
        breadth = self._dict(market.get("breadth"))
        row = {
            "index_symbol": self._optional_text(market.get("index_symbol") or market.get("display_symbol")),
            "vnindex": self._number(market.get("vnindex"), market.get("close_index")),
            "change": self._number(market.get("change")),
            "change_percent": self._number(market.get("change_percent")),
            "trading_value_billion": self._number(market.get("trading_value_billion"), market.get("total_value")),
            "total_volume": self._number(market.get("total_volume")),
            "foreign_net": self._number(market.get("foreign_net")),
            "market_health_score": self._number(market.get("market_health_score"), market.get("regime_score")),
            "regime": self._optional_text(market.get("regime") or market.get("status")),
            "updated_at": self._optional_text(market.get("updated_at")),
        }
        if any(breadth.get(key) is not None for key in ("advancers", "decliners", "unchanged")):
            row.update(
                {
                    "breadth_advancers": self._number(breadth.get("advancers")),
                    "breadth_decliners": self._number(breadth.get("decliners")),
                    "breadth_unchanged": self._number(breadth.get("unchanged")),
                }
            )
        rows = [row] if any(value is not None and value != "" for value in row.values()) else []
        columns = [
            VisualizationColumn(name="index_symbol", type="string", label="Chỉ số"),
            VisualizationColumn(name="vnindex", type="number", label="VNINDEX"),
            VisualizationColumn(name="change", type="number", label="Thay đổi"),
            VisualizationColumn(name="change_percent", type="number", label="% thay đổi", unit="%"),
            VisualizationColumn(name="trading_value_billion", type="number", label="Giá trị giao dịch"),
            VisualizationColumn(name="total_volume", type="number", label="Tổng khối lượng"),
            VisualizationColumn(name="foreign_net", type="number", label="Khối ngoại ròng"),
            VisualizationColumn(name="market_health_score", type="number", label="Sức khỏe thị trường"),
            VisualizationColumn(name="regime", type="string", label="Trạng thái"),
            VisualizationColumn(name="updated_at", type="datetime", label="Cập nhật"),
        ]
        if rows and "breadth_advancers" in rows[0]:
            columns.extend(
                [
                    VisualizationColumn(name="breadth_advancers", type="number", label="Mã tăng"),
                    VisualizationColumn(name="breadth_decliners", type="number", label="Mã giảm"),
                    VisualizationColumn(name="breadth_unchanged", type="number", label="Mã đứng giá"),
                ]
            )
        return self._table(name="market_context", title="Bối cảnh thị trường", columns=columns, rows=rows, source="summary.hose_market_context")

    def build_ai_signals_table(self, summary: dict[str, Any]) -> VisualizationTable:
        rows: list[dict[str, Any]] = []
        rows.extend(self._signal_rows("strength", summary.get("strengths")))
        rows.extend(self._signal_rows("risk", summary.get("weaknesses") or summary.get("risks")))
        decision = self._dict(summary.get("system_decision"))
        for reason in self._string_list(decision.get("reasons")):
            rows.append({"signal_type": "decision_reason", "title": self._optional_text(decision.get("status")), "content": reason})
        for scenario in self._list(summary.get("scenarios") or summary.get("forecast_scenarios")):
            rows.append(
                {
                    "signal_type": "scenario",
                    "title": self._optional_text(scenario.get("scenario") or scenario.get("name")),
                    "content": self._optional_text(scenario.get("expected_behavior") or scenario.get("condition") or scenario.get("summary")),
                    "status": self._optional_text(scenario.get("status")),
                    "probability_pct": self._number(scenario.get("probability_pct") or scenario.get("probability")),
                    "source_basis": self._optional_text(scenario.get("source_basis")),
                }
            )
        action_plan = self._dict(summary.get("action_plan"))
        for bucket, items in action_plan.items():
            for item in self._list(items):
                rows.append(
                    {
                        "signal_type": "action_plan",
                        "timeframe": bucket,
                        "title": self._optional_text(item.get("action") or item.get("label")),
                        "content": self._optional_text(item.get("condition") or item.get("note") or item.get("risk_note")),
                        "status": self._optional_text(item.get("status")),
                        "source_basis": self._optional_text(item.get("source_basis")),
                    }
                )
        for item in self._list(summary.get("checklist")):
            rows.append(
                {
                    "signal_type": "checklist",
                    "title": self._optional_text(item.get("label") or item.get("item")),
                    "content": self._optional_text(item.get("note") or item.get("description")),
                    "status": self._optional_text(item.get("status")),
                    "source_basis": self._optional_text(item.get("source_basis")),
                }
            )
        for item in self._list(summary.get("evidence_table")):
            rows.append(
                {
                    "signal_type": "evidence",
                    "title": self._optional_text(item.get("title") or item.get("source")),
                    "content": self._optional_text(item.get("fact") or item.get("summary") or item.get("snippet")),
                    "source_basis": self._optional_text(item.get("source") or item.get("source_url")),
                }
            )
        return self._table(
            name="ai_signals",
            title="Tín hiệu AI và luận điểm",
            columns=[
                VisualizationColumn(name="signal_type", type="string", label="Loại tín hiệu"),
                VisualizationColumn(name="timeframe", type="string", label="Khung thời gian"),
                VisualizationColumn(name="title", type="string", label="Tiêu đề"),
                VisualizationColumn(name="content", type="string", label="Nội dung"),
                VisualizationColumn(name="status", type="string", label="Trạng thái"),
                VisualizationColumn(name="probability_pct", type="number", label="Xác suất", unit="%"),
                VisualizationColumn(name="source_basis", type="string", label="Cơ sở nguồn"),
            ],
            rows=rows,
            source="summary.llm_and_presentation_fields",
        )

    def build_data_quality_table(self, data: dict[str, Any], summary: dict[str, Any], derived_notes: list[str]) -> VisualizationTable:
        rows: list[dict[str, Any]] = []
        data_quality = self._dict(summary.get("data_quality"))
        coverage = self._dict(summary.get("data_coverage"))
        for field in self._string_list(data_quality.get("missing_fields") or data_quality.get("missingFields")):
            rows.append({"category": "missing_field", "field": field, "status": "missing", "detail": ""})
        for field in self._missing_from_coverage(coverage):
            rows.append({"category": "coverage", "field": field, "status": "missing", "detail": ""})
        for warning in [*self._string_list(data.get("warnings")), *self._string_list(data_quality.get("warnings"))]:
            rows.append({"category": "warning", "field": "", "status": "warning", "detail": warning})
        for source in sanitize_data_source_statuses(self._list(data.get("data_sources"))):
            rows.append(
                {
                    "category": "source_status",
                    "field": source.get("name"),
                    "status": source.get("status"),
                    "detail": source.get("detail") or source.get("type") or "",
                }
            )
        for note in self._dedupe_strings(derived_notes):
            rows.append({"category": "derived_field", "field": note.split(" ", 1)[0], "status": "derived", "detail": note})
        return self._table(
            name="data_quality",
            title="Độ phủ dữ liệu và cảnh báo",
            columns=[
                VisualizationColumn(name="category", type="string", label="Nhóm"),
                VisualizationColumn(name="field", type="string", label="Trường"),
                VisualizationColumn(name="status", type="string", label="Trạng thái"),
                VisualizationColumn(name="detail", type="string", label="Chi tiết"),
            ],
            rows=rows,
            source="summary.data_quality|data.data_sources|data.warnings",
        )

    def table_to_csv(self, dataset: VisualizationDatasetData, table_name: str) -> str:
        table = next((item for item in dataset.tables if item.name == table_name), None)
        if table is None:
            raise ValueError(f"Unknown visualization table: {table_name}")
        columns = [column.name for column in table.columns] or self._union_row_keys(table.rows)
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow([self._sanitize_csv_cell(name) for name in columns])
        for row in table.rows:
            writer.writerow([self._sanitize_csv_cell(row.get(column)) for column in columns])
        return output.getvalue()

    def _price_volume_chart(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        rows = [row for row in rows if self._optional_text(row.get("date")) and self._number(row.get("close")) is not None][-260:]
        if len(rows) < 2:
            return self._empty_chart("price_volume", "Giá & khối lượng", "Chưa đủ dữ liệu giá để vẽ biểu đồ.")
        labels = [row["date"] for row in rows]
        ohlc = [[row.get("open"), row.get("close"), row.get("low"), row.get("high")] for row in rows]
        volumes = [row.get("volume") for row in rows]
        series = [
            {
                "name": "Giá",
                "type": "candlestick",
                "data": ohlc,
                "xAxisIndex": 0,
                "yAxisIndex": 0,
                "itemStyle": {"color": "#16a34a", "color0": "#dc2626", "borderColor": "#15803d", "borderColor0": "#b91c1c"},
            }
        ]
        for name, key, color in (("MA20", "ma20", "#f59e0b"), ("MA50", "ma50", "#7c3aed")):
            values = [row.get(key) for row in rows]
            if self._has_points(values, minimum=2):
                series.append({"name": name, "type": "line", "data": values, "showSymbol": False, "smooth": True, "lineStyle": {"width": 1.6, "color": color}})
        if self._has_points(volumes, minimum=2):
            series.append(
                {
                    "name": "Khối lượng",
                    "type": "bar",
                    "data": volumes,
                    "xAxisIndex": 1,
                    "yAxisIndex": 1,
                    "barMaxWidth": 12,
                    "itemStyle": {"color": "rgba(2,132,199,0.45)"},
                }
            )
        return self._chart(
            "price_volume",
            "Giá & khối lượng",
            420,
            {
                **self._base_option(),
                "legend": {"top": 0, "left": 8, "itemWidth": 12, "itemHeight": 8, "textStyle": {"fontSize": 11, "color": "#475569"}},
                "grid": [{"left": 56, "right": 24, "top": 38, "height": "58%"}, {"left": 56, "right": 24, "bottom": 28, "height": "18%"}],
                "xAxis": [
                    self._category_axis(labels, grid_index=0, show_labels=True),
                    self._category_axis(labels, grid_index=1, show_labels=True),
                ],
                "yAxis": [
                    self._value_axis("Giá", formatter="{value}", grid_index=0),
                    self._value_axis("Khối lượng", formatter=self._echarts_compact_formatter(), grid_index=1, split_line=False),
                ],
                "dataZoom": [
                    {"type": "inside", "xAxisIndex": [0, 1], "start": 55 if len(rows) > 90 else 0, "end": 100},
                    {"type": "slider", "xAxisIndex": [0, 1], "height": 16, "bottom": 4, "start": 55 if len(rows) > 90 else 0, "end": 100},
                ],
                "series": series,
            },
        )

    def _technical_charts(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = [row for row in rows if self._optional_text(row.get("date"))][-260:]
        if len(rows) < 2:
            return [self._empty_chart("return_drawdown", "Biến động & drawdown", "Chưa đủ dữ liệu kỹ thuật.")]
        labels = [row["date"] for row in rows]
        charts: list[dict[str, Any]] = []
        return_series = self._line_series(rows, [("Biến động ngày", "return_pct", "#2563eb"), ("Drawdown", "drawdown_pct", "#dc2626")])
        if return_series:
            charts.append(
                self._chart(
                    "return_drawdown",
                    "Biến động & drawdown",
                    320,
                    {
                        **self._base_option(percent=True),
                        "legend": self._legend(),
                        "grid": self._single_grid(),
                        "xAxis": self._category_axis(labels),
                        "yAxis": self._value_axis("%", formatter="{value}%"),
                        "series": return_series,
                    },
                )
            )
        rsi_values = [row.get("rsi_14") for row in rows]
        if self._has_points(rsi_values, minimum=10):
            charts.append(
                self._chart(
                    "rsi_14",
                    "RSI 14",
                    300,
                    {
                        **self._base_option(),
                        "grid": self._single_grid(),
                        "xAxis": self._category_axis(labels),
                        "yAxis": {"type": "value", "min": 0, "max": 100, "axisLabel": {"color": "#64748b"}, "splitLine": {"lineStyle": {"color": "#e5e7eb"}}},
                        "series": [{"name": "RSI 14", "type": "line", "data": rsi_values, "showSymbol": False, "smooth": True, "lineStyle": {"width": 2, "color": "#16a34a"}}],
                    },
                )
            )
        return charts or [self._empty_chart("technical_indicators", "Chỉ báo kỹ thuật", "Chưa đủ dữ liệu kỹ thuật.")]

    def _financial_chart(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        rows = [row for row in rows if self._optional_text(row.get("period"))]
        if len(rows) < 2:
            return self._empty_chart("financial_periods", "Kết quả kinh doanh", "Chưa đủ dữ liệu tài chính để vẽ biểu đồ.")
        labels = [row["period"] for row in rows]
        bar_series = self._bar_series(
            rows,
            [("Doanh thu", "revenue", "#2563eb"), ("Lợi nhuận gộp", "gross_profit", "#0f766e"), ("LNST", "profit_after_tax", "#16a34a")],
        )
        eps_values = [row.get("eps") for row in rows]
        series = list(bar_series)
        y_axis = [self._value_axis("Giá trị", formatter=self._echarts_compact_formatter())]
        if self._has_points(eps_values, minimum=2):
            y_axis.append(self._value_axis("EPS", formatter="{value}", split_line=False))
            series.append({"name": "EPS", "type": "line", "data": eps_values, "yAxisIndex": 1, "showSymbol": False, "lineStyle": {"width": 2, "color": "#f59e0b"}})
        if not series:
            return self._empty_chart("financial_periods", "Kết quả kinh doanh", "Chưa đủ dữ liệu tài chính để vẽ biểu đồ.")
        return self._chart(
            "financial_periods",
            "Kết quả kinh doanh",
            360,
            {**self._base_option(), "legend": self._legend(), "grid": self._single_grid(right=46 if len(y_axis) > 1 else 24), "xAxis": self._category_axis(labels), "yAxis": y_axis, "series": series},
        )

    def _profitability_chart(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        rows = [row for row in rows if self._optional_text(row.get("period"))]
        labels = [row["period"] for row in rows]
        series = self._line_series(rows, [("ROE", "roe", "#2563eb"), ("ROA", "roa", "#16a34a")])
        debt_values = [row.get("debt_to_equity") for row in rows]
        y_axis = [self._value_axis("%", formatter="{value}%")]
        if self._has_points(debt_values, minimum=2):
            y_axis.append(self._value_axis("Nợ/VCSH", formatter="{value}", split_line=False))
            series.append({"name": "Nợ/VCSH", "type": "line", "data": debt_values, "yAxisIndex": 1, "showSymbol": False, "smooth": True, "lineStyle": {"width": 2, "color": "#dc2626"}})
        if len(rows) < 2 or not series:
            return self._empty_chart("profitability_leverage", "ROE, ROA & đòn bẩy", "Chưa đủ dữ liệu ROE/ROA hoặc nợ/vốn chủ.")
        return self._chart(
            "profitability_leverage",
            "ROE, ROA & đòn bẩy",
            340,
            {**self._base_option(percent=True), "legend": self._legend(), "grid": self._single_grid(right=48 if len(y_axis) > 1 else 24), "xAxis": self._category_axis(labels), "yAxis": y_axis, "series": series},
        )

    def _scores_chart(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        score_map = {str(row.get("category") or ""): row.get("score_value") for row in rows if self._number(row.get("score_value")) is not None}
        order = [("valuation", "Định giá"), ("quality", "Chất lượng"), ("growth", "Tăng trưởng"), ("momentum", "Động lượng"), ("liquidity", "Thanh khoản"), ("size", "Quy mô"), ("risk", "Rủi ro"), ("data_confidence", "Tin cậy")]
        values = [(key, label, self._number(score_map.get(key))) for key, label in order]
        values = [(key, label, value) for key, label, value in values if value is not None]
        if len(values) < 4:
            return None
        return self._chart(
            "scores",
            "Điểm định lượng",
            340,
            {
                **self._base_option(),
                "radar": {"indicator": [{"name": label, "max": 100} for _, label, _ in values], "radius": "62%", "axisName": {"color": "#475569", "fontSize": 11}},
                "series": [{"name": "Điểm", "type": "radar", "data": [{"value": [value for _, _, value in values], "name": "Điểm"}], "areaStyle": {"color": "rgba(37,99,235,0.14)"}, "lineStyle": {"color": "#2563eb"}}],
            },
        )

    def _peer_chart(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        clean_rows = []
        for row in rows:
            label = self._optional_text(row.get("peer_symbol") or row.get("symbol") or row.get("company"))
            if not label or label.lower() in {"none", "null", "nan", "chưa xác minh"}:
                continue
            if not any(self._number(row.get(key)) is not None for key in ("pe", "pb", "roe", "market_cap")):
                continue
            clean_rows.append({**row, "_label": label})
        clean_rows = clean_rows[:8]
        if len(clean_rows) < 2:
            return None
        labels = [row["_label"] for row in clean_rows]
        series = self._bar_series(clean_rows, [("P/E", "pe", "#2563eb"), ("P/B", "pb", "#0f766e"), ("ROE", "roe", "#16a34a")])
        if not series:
            return None
        return self._chart(
            "peer_comparison",
            "So sánh cùng ngành",
            360,
            {**self._base_option(), "legend": self._legend(), "grid": self._single_grid(bottom=54), "xAxis": self._category_axis(labels, rotate=24), "yAxis": self._value_axis("Chỉ số"), "series": series},
        )

    def _market_chart(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        rows = [row for row in rows if any(self._number(row.get(key)) is not None for key in ("vnindex", "trading_value_billion"))]
        if len(rows) < 1:
            return None
        labels = [self._optional_text(row.get("index_symbol")) or "VNINDEX" for row in rows]
        series = self._bar_series(rows, [("VNINDEX", "vnindex", "#2563eb"), ("GTGD", "trading_value_billion", "#16a34a")])
        if not series:
            return None
        return self._chart(
            "market_context",
            "Bối cảnh thị trường",
            300,
            {**self._base_option(), "legend": self._legend(), "grid": self._single_grid(), "xAxis": self._category_axis(labels), "yAxis": self._value_axis("Giá trị", formatter=self._echarts_compact_formatter()), "series": series},
        )

    def _chart(self, chart_id: str, title: str, height: int, option: dict[str, Any]) -> dict[str, Any]:
        return {"id": chart_id, "title": title, "type": "echarts", "height": height, "option": option}

    def _empty_chart(self, chart_id: str, title: str, message: str) -> dict[str, Any]:
        return {"id": chart_id, "title": title, "type": "empty", "message": message}

    def _base_option(self, *, percent: bool = False) -> dict[str, Any]:
        return {
            "animation": False,
            "color": ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0f766e"],
            "tooltip": {"trigger": "axis", "confine": True, "appendToBody": True, "textStyle": {"fontSize": 11}},
        }

    def _legend(self) -> dict[str, Any]:
        return {"top": 0, "left": 8, "itemWidth": 12, "itemHeight": 8, "textStyle": {"fontSize": 11, "color": "#475569"}}

    def _single_grid(self, *, right: int = 24, bottom: int = 34) -> dict[str, Any]:
        return {"left": 54, "right": right, "top": 42, "bottom": bottom, "containLabel": True}

    def _category_axis(self, labels: list[str], *, grid_index: int | None = None, show_labels: bool = True, rotate: int = 0) -> dict[str, Any]:
        axis: dict[str, Any] = {
            "type": "category",
            "data": labels,
            "axisLabel": {"color": "#64748b", "fontSize": 10, "hideOverlap": True, "rotate": rotate, "show": show_labels},
            "axisLine": {"lineStyle": {"color": "#cbd5e1"}},
            "axisTick": {"show": False},
        }
        if grid_index is not None:
            axis["gridIndex"] = grid_index
        return axis

    def _value_axis(self, name: str, *, formatter: str | dict[str, Any] = "{value}", grid_index: int | None = None, split_line: bool = True) -> dict[str, Any]:
        axis: dict[str, Any] = {
            "type": "value",
            "name": name,
            "scale": True,
            "nameTextStyle": {"color": "#64748b", "fontSize": 10},
            "axisLabel": {"color": "#64748b", "fontSize": 10, "formatter": formatter},
            "splitLine": {"show": split_line, "lineStyle": {"color": "#e5e7eb"}},
        }
        if grid_index is not None:
            axis["gridIndex"] = grid_index
        return axis

    def _echarts_compact_formatter(self) -> dict[str, Any]:
        return "{value}"

    def _table_rows(self, table_map: dict[str, VisualizationTable], name: str) -> list[dict[str, Any]]:
        table = table_map.get(name)
        return list(table.rows) if table else []

    def _has_points(self, values: list[Any], *, minimum: int) -> bool:
        return len([value for value in values if self._number(value) is not None]) >= minimum

    def _line_series(self, rows: list[dict[str, Any]], definitions: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
        series: list[dict[str, Any]] = []
        for name, key, color in definitions:
            values = [row.get(key) for row in rows]
            if self._has_points(values, minimum=2):
                series.append({"name": name, "type": "line", "data": values, "showSymbol": False, "smooth": True, "lineStyle": {"width": 2, "color": color}})
        return series

    def _bar_series(self, rows: list[dict[str, Any]], definitions: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
        series: list[dict[str, Any]] = []
        for name, key, color in definitions:
            values = [row.get(key) for row in rows]
            if self._has_points(values, minimum=1):
                series.append({"name": name, "type": "bar", "data": values, "barMaxWidth": 28, "itemStyle": {"color": color, "borderRadius": [4, 4, 0, 0]}})
        return series

    def store_signed_dataset(self, dataset_id: str, dataset: VisualizationDatasetData, ttl_seconds: int) -> dict[str, Any]:
        key = str(dataset_id or "").strip()
        if not key:
            raise ValueError("dataset_id is required")
        now_ts = int(time.time())
        expires_at = now_ts + max(60, int(ttl_seconds))
        visualization_path = self.export_visualization_json_file(dataset)
        csv_files: dict[str, str] = {}
        for table in dataset.tables:
            try:
                csv_files[table.name] = str(self.export_csv_file(dataset, table.name))
            except Exception:
                logger.warning(
                    "[signed-dataset] csv_persist_failed dataset_id=%s report_id=%s table=%s",
                    key,
                    dataset.meta.source_report_id,
                    table.name,
                    exc_info=True,
                )
        entry = {
            "dataset_id": key,
            "dataset": dataset,
            "symbol": dataset.symbol,
            "exchange": dataset.exchange,
            "report_id": dataset.meta.source_report_id,
            "created_at": now_ts,
            "expires_at": expires_at,
            "created_at_iso": datetime.fromtimestamp(now_ts, timezone.utc).isoformat(),
            "expires_at_iso": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
            "visualization_cache_path": str(visualization_path),
            "csv_files": csv_files,
            "available_tables": [table.name for table in dataset.tables],
        }
        with self._cache_lock:
            self._cleanup_expired_locked(now_ts)
            self._shared_signed_dataset_cache[key] = entry
        self._write_signed_dataset_metadata(key, entry)
        return dict(entry)

    def get_signed_dataset_entry(self, dataset_id: str) -> dict[str, Any] | None:
        key = str(dataset_id or "").strip()
        if not key:
            return None
        now_ts = int(time.time())
        with self._cache_lock:
            self._cleanup_expired_locked(now_ts)
            cached = self._shared_signed_dataset_cache.get(key)
            if cached is not None:
                if int(cached.get("expires_at", 0)) <= now_ts:
                    self._shared_signed_dataset_cache.pop(key, None)
                    return None
                return dict(cached)
        persisted = self.load_signed_dataset_metadata(key)
        if persisted is None:
            return None
        if int(persisted.get("expires_at", 0)) <= now_ts:
            self._delete_signed_dataset_metadata(key)
            return None
        dataset = self._load_dataset_from_signed_metadata(persisted)
        if dataset is not None:
            persisted["dataset"] = dataset
            with self._cache_lock:
                self._shared_signed_dataset_cache[key] = dict(persisted)
        return persisted

    def get_signed_dataset(self, dataset_id: str) -> VisualizationDatasetData | None:
        entry = self.get_signed_dataset_entry(dataset_id)
        if entry is None:
            return None
        dataset = entry.get("dataset")
        if isinstance(dataset, VisualizationDatasetData):
            return dataset
        return self._load_dataset_from_signed_metadata(entry)

    def signed_dataset_cache_size(self) -> int:
        now_ts = int(time.time())
        with self._cache_lock:
            self._cleanup_expired_locked(now_ts)
            return len(self._shared_signed_dataset_cache)

    @classmethod
    def _cleanup_expired_locked(cls, now_ts: int) -> None:
        expired_keys = [key for key, value in cls._shared_signed_dataset_cache.items() if int(value.get("expires_at", 0)) <= now_ts]
        for key in expired_keys:
            cls._shared_signed_dataset_cache.pop(key, None)

    @classmethod
    def _cleanup_dataset_cache_locked(cls, now_ts: int) -> None:
        expired_keys = [key for key, value in cls._shared_dataset_cache.items() if int(value.get("expires_at", 0)) <= now_ts]
        for key in expired_keys:
            cls._shared_dataset_cache.pop(key, None)

    def _dataset_cache_keys(self, dataset: VisualizationDatasetData, *, chart_range: str | None = None) -> list[str]:
        return self._lookup_dataset_cache_keys(
            symbol=dataset.symbol,
            exchange=dataset.exchange,
            chart_range=chart_range or dataset.meta.chart_range,
            report_id=dataset.meta.source_report_id,
        )

    def _lookup_dataset_cache_keys(
        self,
        *,
        symbol: str | None = None,
        exchange: str | None = None,
        chart_range: str | None = None,
        report_id: str | None = None,
    ) -> list[str]:
        keys: list[str] = []
        clean_report_id = self._safe_part(report_id)
        if clean_report_id:
            keys.append(f"report:{clean_report_id}")
        clean_symbol = normalize_symbol(symbol) if symbol else ""
        clean_exchange = str(exchange or "HOSE").strip().upper() or "HOSE"
        clean_range = str(chart_range or self.settings.visualization_default_chart_range or "1y").strip().lower()
        if clean_symbol:
            keys.append(f"symbol:{clean_symbol}:{clean_exchange}:{clean_range}")
            keys.append(f"symbol:{clean_symbol}:{clean_exchange}")
        return self._dedupe_strings(keys)

    def _export_path(self, dataset: VisualizationDatasetData, table_or_kind: str, extension: str) -> Path:
        report_part = self._safe_part(dataset.meta.source_report_id) or self._safe_part(f"{dataset.symbol}_{dataset.exchange}") or "visualization"
        suffix = self._safe_part(table_or_kind) or "export"
        ext = self._safe_part(extension) or "txt"
        return self._export_dir() / f"{report_part}_{suffix}.{ext}"

    def _export_dir(self) -> Path:
        root = Path(self.settings.data_formulator_home or ".data_formulator")
        if not root.is_absolute():
            root = Path.cwd() / root
        return root / "exports"

    def _signed_dataset_dir(self) -> Path:
        root = Path(self.settings.data_formulator_home or ".data_formulator")
        if not root.is_absolute():
            root = Path.cwd() / root
        return root / "signed_datasets"

    def load_signed_dataset_metadata(self, dataset_id: str | None) -> dict[str, Any] | None:
        key = self._safe_part(dataset_id)
        if not key:
            return None
        path = self._signed_dataset_dir() / f"{key}.json"
        if not path.exists() or not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("[signed-dataset] metadata_read_failed dataset_id=%s path=%s", key, path, exc_info=True)
            return None
        return payload if isinstance(payload, dict) else None

    def _write_signed_dataset_metadata(self, dataset_id: str, entry: dict[str, Any]) -> Path:
        key = self._safe_part(dataset_id)
        path = self._signed_dataset_dir() / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {name: value for name, value in entry.items() if name != "dataset"}
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        os.replace(tmp_path, path)
        return path

    def _delete_signed_dataset_metadata(self, dataset_id: str) -> None:
        key = self._safe_part(dataset_id)
        if not key:
            return
        path = self._signed_dataset_dir() / f"{key}.json"
        try:
            path.unlink(missing_ok=True)
        except Exception:
            logger.debug("[signed-dataset] metadata_delete_failed dataset_id=%s path=%s", key, path, exc_info=True)

    def _load_dataset_from_signed_metadata(self, metadata: dict[str, Any]) -> VisualizationDatasetData | None:
        raw_path = metadata.get("visualization_cache_path")
        if not raw_path:
            report_id = metadata.get("report_id")
            return self.load_visualization_json_file(str(report_id or ""))
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists() or not path.is_file():
            return self.load_visualization_json_file(str(metadata.get("report_id") or ""))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return VisualizationDatasetData.model_validate(payload)
        except Exception:
            logger.warning("[signed-dataset] dataset_load_failed dataset_id=%s path=%s", metadata.get("dataset_id"), path, exc_info=True)
            return None

    def _safe_part(self, value: Any) -> str:
        clean = str(value or "").strip()
        clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", clean)
        return clean.strip("._-")

    def _table(
        self,
        *,
        name: str,
        title: str,
        columns: list[VisualizationColumn],
        rows: list[dict[str, Any]],
        source: str,
    ) -> VisualizationTable:
        limited_rows = rows[: self.settings.visualization_max_rows]
        return VisualizationTable(
            name=name,
            title=title,
            columns=columns,
            rows=limited_rows,
            row_count=len(limited_rows),
            source=source,
        )

    def _sort_price_rows(self, rows: list[Any]) -> list[dict[str, Any]]:
        return sorted([dict(row) for row in rows if isinstance(row, dict)], key=lambda row: self._date_sort_key(row))

    def _sort_financial_periods(self, rows: list[Any]) -> list[dict[str, Any]]:
        return sorted([dict(row) for row in rows if isinstance(row, dict)], key=lambda row: self._period_sort_key(row))

    def _date_value(self, row: dict[str, Any]) -> str | None:
        value = row.get("date") or row.get("time") or row.get("trading_date")
        if value:
            return str(value)[:10]
        time_id = row.get("time_id") or row.get("timeId")
        text = str(time_id or "")
        if len(text) == 8 and text.isdigit():
            return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
        return None

    def _date_sort_key(self, row: dict[str, Any]) -> tuple[str, int]:
        date = self._date_value(row) or ""
        time_id = self._int(row.get("time_id") or row.get("timeId")) or 0
        return (date, time_id)

    def _period_sort_key(self, row: dict[str, Any]) -> tuple[int, int, str]:
        year = self._int(row.get("year"))
        quarter = self._int(row.get("quarter"))
        if year is None or quarter is None:
            match = re.search(r"Q([1-4])\s*/\s*(20\d{2}|19\d{2})", str(row.get("period") or ""), re.IGNORECASE)
            if match:
                quarter = quarter or int(match.group(1))
                year = year or int(match.group(2))
        return (year or 0, quarter or 0, str(row.get("period") or ""))

    def _daily_returns(self, closes: list[float | None]) -> list[float | None]:
        result: list[float | None] = [None]
        for previous, current in zip(closes, closes[1:]):
            if previous in (None, 0) or current is None:
                result.append(None)
            else:
                result.append(self._round(((current / previous) - 1) * 100))
        return result[: len(closes)]

    def _rolling_mean(self, values: list[float | None], window: int) -> list[float | None]:
        result: list[float | None] = []
        for idx in range(len(values)):
            window_values = [value for value in values[max(0, idx - window + 1) : idx + 1] if value is not None]
            result.append(self._round(sum(window_values) / window) if len(window_values) == window else None)
        return result

    def _rolling_volatility(self, returns: list[float | None], window: int) -> list[float | None]:
        result: list[float | None] = []
        for idx in range(len(returns)):
            window_values = [value for value in returns[max(0, idx - window + 1) : idx + 1] if value is not None]
            result.append(self._round(pstdev(window_values)) if len(window_values) == window else None)
        return result

    def _drawdown_series(self, closes: list[float | None]) -> list[float | None]:
        peak: float | None = None
        result: list[float | None] = []
        for close in closes:
            if close is None:
                result.append(None)
                continue
            peak = close if peak is None else max(peak, close)
            result.append(self._round(((close / peak) - 1) * 100) if peak else None)
        return result

    def _rsi_series(self, closes: list[float | None], period: int) -> list[float | None]:
        result: list[float | None] = [None] * len(closes)
        for idx in range(period, len(closes)):
            window = closes[idx - period : idx + 1]
            if any(value is None for value in window):
                continue
            changes = [window[i] - window[i - 1] for i in range(1, len(window))]  # type: ignore[operator]
            gains = [max(change, 0) for change in changes]
            losses = [abs(min(change, 0)) for change in changes]
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
            if avg_loss == 0:
                result[idx] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[idx] = self._round(100 - (100 / (1 + rs)))
        return result

    def _macd_payload(self, closes: list[float | None]) -> dict[str, list[float | None]]:
        ema12 = self._ema_series(closes, 12)
        ema26 = self._ema_series(closes, 26)
        macd = [self._round(a - b) if a is not None and b is not None else None for a, b in zip(ema12, ema26)]
        valid_positions = [idx for idx, value in enumerate(macd) if value is not None]
        valid_values = [macd[idx] for idx in valid_positions]
        signal_valid = self._ema_series(valid_values, 9)  # type: ignore[arg-type]
        signal: list[float | None] = [None] * len(closes)
        for pos, value in zip(valid_positions, signal_valid):
            signal[pos] = value
        histogram = [self._round(m - s) if m is not None and s is not None else None for m, s in zip(macd, signal)]
        return {"macd": macd, "signal": signal, "histogram": histogram}

    def _ema_series(self, values: list[float | None], period: int) -> list[float | None]:
        result: list[float | None] = [None] * len(values)
        clean_count = 0
        ema: float | None = None
        alpha = 2 / (period + 1)
        initial: list[float] = []
        for idx, value in enumerate(values):
            if value is None:
                continue
            clean_count += 1
            if ema is None:
                initial.append(value)
                if clean_count == period:
                    ema = sum(initial) / period
                    result[idx] = self._round(ema)
                continue
            ema = (value - ema) * alpha + ema
            result[idx] = self._round(ema)
        return result

    def _signal_rows(self, signal_type: str, value: Any) -> list[dict[str, Any]]:
        rows = []
        for item in self._list(value):
            if isinstance(item, dict):
                rows.append(
                    {
                        "signal_type": signal_type,
                        "title": self._optional_text(item.get("label") or item.get("title")),
                        "content": self._optional_text(item.get("note") or item.get("content") or item.get("text")),
                        "status": self._optional_text(item.get("status")),
                        "source_basis": self._optional_text(item.get("source_basis")),
                    }
                )
            else:
                rows.append({"signal_type": signal_type, "content": str(item)})
        return rows

    def _missing_from_coverage(self, coverage: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        for key, value in coverage.items():
            if key.endswith("_loaded") and value is False:
                missing.append(key)
        if self._int(coverage.get("price_history_points")) == 0:
            missing.append("price_history")
        if self._int(coverage.get("financial_periods_count")) == 0:
            missing.append("financials.periods")
        return self._dedupe_strings(missing)

    def _generated_at(self, value: Any) -> str:
        if value:
            return str(value)
        try:
            tzinfo = ZoneInfo(self.settings.analyse_timezone)
        except Exception:
            tzinfo = ZoneInfo("UTC")
        return datetime.now(tzinfo).isoformat()

    def _reason_text(self, value: Any) -> str | None:
        if value in (None, "", [], {}):
            return None
        if isinstance(value, list):
            return "; ".join(str(item) for item in value if str(item).strip())
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, default=str)
        return str(value)

    def _union_row_keys(self, rows: list[dict[str, Any]]) -> list[str]:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        return keys

    def _sanitize_csv_cell(self, value: Any) -> str:
        if value is None:
            text = ""
        elif isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, default=str)
        elif isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = str(value)
        text = self._scrub_sensitive_markers(scrub_debug_text(text))
        if text.startswith(("=", "+", "-", "@")):
            return "'" + text
        return text

    def _scrub_visualization_payload(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {self._scrub_sensitive_markers(str(key)): self._scrub_visualization_payload(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._scrub_visualization_payload(item) for item in value]
        if isinstance(value, str):
            return self._scrub_sensitive_markers(value)
        return value

    def _scrub_sensitive_markers(self, value: str) -> str:
        text = str(value)
        for marker in (
            "Authorization",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "BACKEND_API_TOKEN",
            "AI_REPORT_DB_URL",
            "Bearer",
            "mssql+pyodbc",
        ):
            text = re.sub(re.escape(marker), "<redacted>", text, flags=re.IGNORECASE)
        return text

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list(self, value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if value in (None, "", {}, []):
            return []
        return [str(value)]

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = str(value or "").strip()
            if not clean or clean in seen:
                continue
            result.append(clean)
            seen.add(clean)
        return result

    def _optional_text(self, value: Any) -> str | None:
        clean = str(value or "").strip()
        return clean or None

    def _number(self, *values: Any) -> float | None:
        for value in values:
            if isinstance(value, bool) or value in (None, ""):
                continue
            if isinstance(value, (int, float)):
                numeric = float(value)
            else:
                text = str(value).strip().replace(",", "")
                try:
                    numeric = float(text)
                except ValueError:
                    continue
            if math.isfinite(numeric):
                return numeric
        return None

    def _int(self, value: Any) -> int | None:
        number = self._number(value)
        return int(number) if number is not None else None

    def _round(self, value: float | None, digits: int = 4) -> float | None:
        if value is None or not math.isfinite(value):
            return None
        return round(value, digits)

    def _normalize_confidence(self, value: Any) -> float | None:
        number = self._number(value)
        if number is None:
            return None
        if 0 <= number <= 1:
            number *= 100
        return self._round(max(0, min(100, number)), 2)
