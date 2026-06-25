from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import math
from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.services.stock_data_service import FINANCIAL_METRIC_FIELDS, StockDataService
from analyse.utils.datetime_utils import now_iso
from analyse.utils.debug_scrub import scrub_debug_payload
from analyse.utils.symbol_utils import normalize_symbol


class FinancialSourceMergeService:
    """Merge Backend/Vietstock/CafeF financial periods without overwriting primary data."""

    CAFEF_SOURCE = "CafeF tài chính"
    VIETSTOCK_SOURCE = "Vietstock Finance BCTC"
    BACKEND_SOURCE = "Backend analysis-data"

    def __init__(self, settings: Settings | None = None, stock_data_service: StockDataService | None = None) -> None:
        self.settings = settings or get_settings()
        self.stock_data_service = stock_data_service or StockDataService()

    def merge(
        self,
        stock_detail: dict[str, Any],
        source_payloads: list[dict[str, Any]],
        *,
        symbol: str,
        exchange: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        normalized = self.stock_data_service.normalize_analysis_data(stock_detail)
        if not self.settings.enable_financial_source_merge:
            return normalized, self._empty_report(symbol, exchange, reason="ENABLE_FINANCIAL_SOURCE_MERGE=false")

        primary_financials = self._dict(normalized.get("financials"))
        primary_periods = self.stock_data_service.sanitize_financial_periods(self._list(primary_financials.get("periods")))
        primary_source_name = self._primary_source_name(normalized)
        sources = [
            {
                "source_key": "backend_analysis_data",
                "source": primary_source_name,
                "source_url": primary_financials.get("source_url"),
                "periods": primary_periods,
                "status": "success" if self.stock_data_service.valid_financial_periods(primary_periods) else "insufficient",
            }
        ]
        sources.extend(self._normalize_source_payload(payload) for payload in source_payloads if isinstance(payload, dict))
        sources = self._sort_sources(sources)

        merged_by_period: dict[str, dict[str, Any]] = {}
        contributions: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        cross_checks: list[dict[str, Any]] = []
        backfilled_by_source: list[dict[str, Any]] = []
        not_backfilled: list[dict[str, Any]] = []
        before_missing: list[dict[str, Any]] = []
        source_metrics: dict[str, int] = {}
        source_periods: dict[str, set[str]] = {}

        for source in sources:
            source_name = str(source.get("source") or "Nguồn tài chính")
            source_periods.setdefault(source_name, set())
            sanitized_periods = self.stock_data_service.sanitize_financial_periods(self._list(source.get("periods")))
            usable_periods = self.stock_data_service.valid_financial_periods(sanitized_periods)
            source_metrics[source_name] = self._metric_cell_count(usable_periods)
            for period in usable_periods:
                period_key = self._period_key(period)
                if not period_key:
                    continue
                source_periods[source_name].add(period_key)
                if period_key not in merged_by_period:
                    merged = self._period_with_sources(period, source_name, source.get("source_url"))
                    merged_by_period[period_key] = merged
                    for field, value in self._numeric_fields(period).items():
                        contribution = self._contribution(source_name, period_key, field, "added_period", value)
                        contributions.append(contribution)
                        if source_name == self.CAFEF_SOURCE:
                            backfilled_by_source.append(contribution)
                    continue

                target = merged_by_period[period_key]
                for field, value in self._numeric_fields(period).items():
                    existing = self._numeric(target.get(field))
                    if existing is None:
                        before_missing.append({"source": source_name, "field": field, "period": period_key})
                        if self.settings.financial_allow_supplementary_backfill and (
                            not self.settings.financial_require_source_for_backfill or source_name
                        ):
                            target[field] = value
                            self._set_field_source(target, field, source_name, source.get("source_url"))
                            contribution = self._contribution(source_name, period_key, field, "filled_missing", value)
                            contributions.append(contribution)
                            if source_name == self.CAFEF_SOURCE:
                                backfilled_by_source.append(contribution)
                        else:
                            not_backfilled.append(
                                {
                                    "source": source_name,
                                    "field": field,
                                    "period": period_key,
                                    "reason": "Supplementary backfill is disabled by configuration",
                                }
                            )
                        continue

                    difference_pct = self._difference_pct(existing, value)
                    if difference_pct is not None and difference_pct > float(self.settings.financial_conflict_tolerance_pct):
                        conflict = {
                            "field": field,
                            "period": period_key,
                            "primary_source": self._field_source(target, field) or primary_source_name,
                            "secondary_source": source_name,
                            "primary_value": existing,
                            "secondary_value": value,
                            "difference_pct": round(difference_pct, 4),
                            "resolution": "kept_primary",
                        }
                        conflicts.append(conflict)
                        if source_name == self.CAFEF_SOURCE:
                            not_backfilled.append({**conflict, "reason": "Primary source already has a conflicting value"})
                    elif source_name != self._field_source(target, field):
                        cross_checks.append(
                            {
                                "field": field,
                                "period": period_key,
                                "primary_source": self._field_source(target, field) or primary_source_name,
                                "secondary_source": source_name,
                                "primary_value": existing,
                                "secondary_value": value,
                                "difference_pct": round(difference_pct or 0.0, 4),
                                "resolution": "cross_checked",
                            }
                        )

        merged_periods = self._sort_periods(list(merged_by_period.values()))
        merged_valid_periods = self.stock_data_service.valid_financial_periods(merged_periods)
        financials = dict(primary_financials)
        financials["periods"] = merged_valid_periods
        financials["source"] = self._merged_source_label(contributions, primary_source_name)
        financials["source_contributions"] = contributions
        financials["conflicts"] = conflicts
        financials["cross_checks"] = cross_checks[:100]
        financials["merged_at"] = now_iso()
        normalized["financials"] = financials
        normalized["financials_merged"] = {
            "periods": merged_valid_periods,
            "source": financials["source"],
            "source_contributions": contributions,
            "conflicts": conflicts,
            "cross_checks": cross_checks[:100],
        }
        normalized["financial_source_contributions"] = contributions
        normalized["financial_conflicts"] = conflicts
        normalized["financial_cross_checks"] = cross_checks[:100]

        cafef_report = self._cafef_contribution_report(
            sources=sources,
            source_metrics=source_metrics,
            source_periods=source_periods,
            contributions=contributions,
            conflicts=conflicts,
            backfilled=backfilled_by_source,
        )
        normalized["cafef_financial_contribution"] = cafef_report

        backfill_report = {
            "before_backfill": {
                "missing_fields_count": len(before_missing),
                "missing_fields": before_missing,
            },
            "after_backfill": {
                "missing_fields_count": len(not_backfilled),
                "missing_fields": [
                    {"field": item.get("field"), "period": item.get("period"), "reason": item.get("reason")}
                    for item in not_backfilled
                ],
            },
            "backfilled_by_source": backfilled_by_source,
            "not_backfilled": not_backfilled,
            "conflicts": conflicts,
        }
        normalized["financial_backfill_report"] = backfill_report
        normalized["_financial_merge_report"] = {
            "symbol": normalize_symbol(symbol),
            "exchange": exchange,
            "generated_at": now_iso(),
            "periods_count": len(merged_valid_periods),
            "source_contributions": contributions,
            "conflicts": conflicts,
            "cross_checks_count": len(cross_checks),
            "cafef_financial_contribution": cafef_report,
            "backfill_report": backfill_report,
        }
        self._update_data_quality(normalized, merged_valid_periods, cafef_report, contributions)
        self._update_financial_balance(normalized, merged_valid_periods)
        self._save_backfill_debug(symbol, normalized["_financial_merge_report"])
        return normalized, normalized["_financial_merge_report"]

    def _normalize_source_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_name = self._display_source_name(payload.get("source") or payload.get("name"))
        return {
            "source_key": self._source_key(source_name),
            "source": source_name,
            "source_url": payload.get("source_url"),
            "periods": payload.get("periods") if isinstance(payload.get("periods"), list) else [],
            "status": payload.get("status") or "partial",
            "financial_ratios_only": bool(payload.get("financial_ratios_only")),
            "audit": payload.get("audit") if isinstance(payload.get("audit"), dict) else {},
        }

    def _sort_sources(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        priority = {key: index for index, key in enumerate(self.settings.financial_source_priority_list)}
        return sorted(sources, key=lambda item: priority.get(str(item.get("source_key") or ""), 999))

    def _source_key(self, source_name: str) -> str:
        text = str(source_name or "").strip().lower()
        if "cafef" in text:
            return "cafef_financial"
        if "vietstock" in text:
            return "vietstock_bctc"
        return "backend_analysis_data"

    def _display_source_name(self, source_name: Any) -> str:
        text = str(source_name or "").strip()
        lower = text.lower()
        if "cafef" in lower:
            return self.CAFEF_SOURCE
        if "vietstock" in lower:
            return self.VIETSTOCK_SOURCE
        if text:
            return text
        return self.BACKEND_SOURCE

    def _primary_source_name(self, normalized: dict[str, Any]) -> str:
        financials = self._dict(normalized.get("financials"))
        data_quality = self._dict(normalized.get("data_quality"))
        return self._display_source_name(financials.get("source") or data_quality.get("financial_source") or self.BACKEND_SOURCE)

    def _merged_source_label(self, contributions: list[dict[str, Any]], primary_source: str) -> str:
        sources = [primary_source]
        if any(item.get("source") == self.VIETSTOCK_SOURCE for item in contributions):
            sources.append(self.VIETSTOCK_SOURCE)
        if any(item.get("source") == self.CAFEF_SOURCE for item in contributions):
            sources.append("Nguồn bổ sung: CafeF tài chính")
        result: list[str] = []
        for source in sources:
            if source and source not in result:
                result.append(source)
        return " / ".join(result)

    def _period_with_sources(self, period: dict[str, Any], source: str, source_url: Any) -> dict[str, Any]:
        clean = deepcopy(period)
        clean.setdefault("_period_source", source)
        clean.setdefault("_field_sources", {})
        clean.setdefault("_field_source_urls", {})
        for field in self._numeric_fields(clean):
            self._set_field_source(clean, field, source, source_url)
        return clean

    def _set_field_source(self, period: dict[str, Any], field: str, source: str, source_url: Any) -> None:
        field_sources = period.get("_field_sources") if isinstance(period.get("_field_sources"), dict) else {}
        field_urls = period.get("_field_source_urls") if isinstance(period.get("_field_source_urls"), dict) else {}
        field_sources[field] = source
        if source_url:
            field_urls[field] = source_url
        period["_field_sources"] = field_sources
        period["_field_source_urls"] = field_urls

    def _field_source(self, period: dict[str, Any], field: str) -> str | None:
        sources = period.get("_field_sources") if isinstance(period.get("_field_sources"), dict) else {}
        value = sources.get(field)
        return str(value) if value else None

    def _contribution(self, source: str, period: str, field: str, action: str, value: float) -> dict[str, Any]:
        return {
            "source": source,
            "period": period,
            "field": field,
            "action": action,
            "value": value,
        }

    def _cafef_contribution_report(
        self,
        *,
        sources: list[dict[str, Any]],
        source_metrics: dict[str, int],
        source_periods: dict[str, set[str]],
        contributions: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
        backfilled: list[dict[str, Any]],
    ) -> dict[str, Any]:
        cafef_sources = [source for source in sources if source.get("source") == self.CAFEF_SOURCE]
        raw_status = str((cafef_sources[-1] if cafef_sources else {}).get("status") or "skipped")
        metrics_count = int(source_metrics.get(self.CAFEF_SOURCE) or 0)
        periods_count = len(source_periods.get(self.CAFEF_SOURCE) or set())
        filled = [item for item in contributions if item.get("source") == self.CAFEF_SOURCE and item.get("action") in {"filled_missing", "added_period"}]
        conflicts_count = sum(1 for item in conflicts if item.get("secondary_source") == self.CAFEF_SOURCE)
        if raw_status in {"disabled", "failed"}:
            status = raw_status
        elif filled:
            status = "success"
        elif metrics_count > 0:
            status = "partial"
        else:
            status = "insufficient" if cafef_sources else "skipped"
        return {
            "source": self.CAFEF_SOURCE,
            "status": status,
            "raw_status": raw_status,
            "filled_fields_count": len(filled),
            "periods_count": periods_count,
            "metrics_count": metrics_count,
            "conflicts_count": conflicts_count,
            "merge_contributions": filled,
            "contributed_fields": sorted({str(item.get("field")) for item in filled if item.get("field")}),
            "backfilled_fields": backfilled,
        }

    def _update_data_quality(
        self,
        normalized: dict[str, Any],
        periods: list[dict[str, Any]],
        cafef_report: dict[str, Any],
        contributions: list[dict[str, Any]],
    ) -> None:
        data_quality = dict(self._dict(normalized.get("data_quality")))
        full_periods = self.stock_data_service.full_financial_periods(periods)
        ratio_periods = self.stock_data_service.ratio_financial_periods(periods)
        data_quality["financials_loaded"] = bool(full_periods)
        data_quality["financial_periods_count"] = len(full_periods)
        data_quality["financial_ratios_loaded"] = bool(ratio_periods)
        data_quality["financial_ratio_periods_count"] = len(ratio_periods)
        data_quality["financial_source"] = self._dict(normalized.get("financials")).get("source")
        data_quality["financial_source_contributions"] = contributions
        data_quality["cafef_financial_contribution"] = cafef_report
        missing = data_quality.get("missing_fields") if isinstance(data_quality.get("missing_fields"), list) else []
        if full_periods:
            data_quality["missing_fields"] = [
                item for item in missing if item not in {"financials", "financials.periods", "bctc", "bctc_3q"}
            ]
        warnings = list(data_quality.get("warnings") or [])
        filled_count = int(cafef_report.get("filled_fields_count") or 0)
        if any(item.get("source") == self.VIETSTOCK_SOURCE for item in contributions):
            warnings.append("Báo cáo đã bổ sung dữ liệu tài chính từ Vietstock Finance để đối chiếu với dữ liệu nội bộ.")
        if filled_count:
            warnings.append(f"CafeF tài chính đã bù {filled_count} chỉ tiêu/kỳ tài chính còn thiếu.")
        data_quality["warnings"] = self._dedupe_strings(warnings)
        normalized["data_quality"] = data_quality

    def _update_financial_balance(self, normalized: dict[str, Any], periods: list[dict[str, Any]]) -> None:
        if not periods:
            return
        latest = periods[0]
        balance = dict(self._dict(normalized.get("financial_balance")))
        for key in FINANCIAL_METRIC_FIELDS:
            if key in balance and balance.get(key) not in (None, ""):
                continue
            if latest.get(key) not in (None, ""):
                balance[key] = latest.get(key)
        if latest.get("period"):
            balance.setdefault("period", latest.get("period"))
        normalized["financial_balance"] = balance

    def _save_backfill_debug(self, symbol: str, payload: dict[str, Any]) -> None:
        if not self.settings.financial_backfill_write_debug:
            return
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            clean_symbol = normalize_symbol(symbol) or "UNKNOWN"
            debug_payload = scrub_debug_payload(payload.get("backfill_report") or payload)
            (debug_dir / f"{clean_symbol}_financial_backfill_report.json").write_text(
                json.dumps(debug_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            return

    def _empty_report(self, symbol: str, exchange: str | None, *, reason: str) -> dict[str, Any]:
        return {
            "symbol": normalize_symbol(symbol),
            "exchange": exchange,
            "generated_at": now_iso(),
            "source_contributions": [],
            "conflicts": [],
            "cafef_financial_contribution": {"source": self.CAFEF_SOURCE, "status": "skipped", "filled_fields_count": 0},
            "backfill_report": {
                "before_backfill": {"missing_fields_count": 0, "missing_fields": []},
                "after_backfill": {"missing_fields_count": 0, "missing_fields": []},
                "backfilled_by_source": [],
                "not_backfilled": [{"reason": reason}],
            },
        }

    def _sort_periods(self, periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(periods, key=lambda item: (int(item.get("year") or 0), int(item.get("quarter") or 0)), reverse=True)

    def _period_key(self, period: dict[str, Any]) -> str | None:
        value = period.get("period")
        if value:
            return str(value)
        year = period.get("year")
        quarter = period.get("quarter")
        if year and quarter:
            return f"Q{quarter}/{year}"
        if year:
            return str(year)
        return None

    def _numeric_fields(self, period: dict[str, Any]) -> dict[str, float]:
        result: dict[str, float] = {}
        for field in FINANCIAL_METRIC_FIELDS:
            numeric = self._numeric(period.get(field))
            if numeric is not None:
                result[field] = numeric
        return result

    def _metric_cell_count(self, periods: list[dict[str, Any]]) -> int:
        return sum(len(self._numeric_fields(period)) for period in periods)

    def _difference_pct(self, primary: float, secondary: float) -> float | None:
        denominator = max(abs(primary), abs(secondary))
        if denominator <= 0:
            return None
        return abs(primary - secondary) / denominator * 100

    def _numeric(self, value: Any) -> float | None:
        if isinstance(value, bool) or value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            numeric = float(value)
            return numeric if math.isfinite(numeric) else None
        try:
            numeric = float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None
        return numeric if math.isfinite(numeric) else None

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def _dedupe_strings(self, values: list[Any]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = str(value).strip()
            if clean and clean not in seen:
                result.append(clean)
                seen.add(clean)
        return result
