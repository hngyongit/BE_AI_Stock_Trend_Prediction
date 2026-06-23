from __future__ import annotations

import re
import unicodedata
from typing import Any


FINANCIAL_METRIC_FIELDS = {
    "revenue",
    "gross_profit",
    "cost_of_goods_sold",
    "financial_income",
    "financial_expense",
    "selling_expense",
    "general_admin_expense",
    "operating_profit",
    "profit_before_tax",
    "profit_after_tax",
    "parent_profit",
    "eps",
    "total_assets",
    "total_liabilities",
    "equity",
    "current_assets",
    "current_liabilities",
    "cash",
    "inventory",
    "short_term_investments",
    "short_term_receivables",
    "other_current_assets",
    "long_term_assets",
    "fixed_assets",
    "investment_properties",
    "long_term_investments",
    "long_term_liabilities",
    "total_capital",
    "owner_capital",
    "share_premium",
    "retained_earnings",
    "pe",
    "pb",
    "roe",
    "roa",
    "eps_ttm",
    "bvps",
    "gross_margin",
    "net_margin",
    "current_ratio",
    "interest_coverage",
    "debt_ratio",
    "debt_to_assets",
    "debt_to_equity",
    "net_interest_income",
    "interest_income",
    "interest_expense",
    "net_fee_income",
    "fx_trading_income",
    "trading_securities_income",
    "investment_securities_income",
    "dividend_income",
    "operating_expense",
    "pre_provision_operating_profit",
    "credit_provision_expense",
    "deposit_at_state_bank",
    "cash_and_gold",
    "interbank_assets",
    "customer_loans",
    "loan_loss_reserve",
    "trading_securities",
    "investment_securities",
    "government_and_state_bank_debt",
    "interbank_liabilities",
    "customer_deposits",
    "valuable_papers_issued",
    "npl_ratio",
    "loan_loss_coverage",
    "nim",
    "casa_ratio",
}

FULL_BCTC_METRIC_FIELDS = {
    "revenue",
    "gross_profit",
    "operating_profit",
    "profit_before_tax",
    "profit_after_tax",
    "parent_profit",
    "total_assets",
    "total_liabilities",
    "equity",
    "net_interest_income",
    "net_fee_income",
    "pre_provision_operating_profit",
    "credit_provision_expense",
    "customer_loans",
    "customer_deposits",
}

FINANCIAL_RATIO_FIELDS = {
    "eps",
    "eps_ttm",
    "bvps",
    "pe",
    "pb",
    "roe",
    "roa",
    "gross_margin",
    "net_margin",
    "current_ratio",
    "interest_coverage",
    "debt_ratio",
    "debt_to_assets",
    "debt_to_equity",
    "npl_ratio",
    "loan_loss_coverage",
    "nim",
    "casa_ratio",
}

BANK_INDICATOR_FIELDS = {
    "net_interest_income",
    "interest_income",
    "interest_expense",
    "net_fee_income",
    "pre_provision_operating_profit",
    "credit_provision_expense",
    "deposit_at_state_bank",
    "cash_and_gold",
    "interbank_assets",
    "customer_loans",
    "loan_loss_reserve",
    "trading_securities",
    "investment_securities",
    "government_and_state_bank_debt",
    "interbank_liabilities",
    "customer_deposits",
    "valuable_papers_issued",
    "npl_ratio",
    "loan_loss_coverage",
    "nim",
    "casa_ratio",
}

ORGANIZATION_HOLDER_MARKERS = {
    "asset",
    "bank",
    "capital",
    "company",
    "corporation",
    "dragon",
    "deutsche",
    "elite",
    "fund",
    "holdings",
    "investment",
    "limited",
    "ltd",
    "management",
    "norges",
    "pyn",
    "securities",
    "vof",
    "vinacapital",
    "cong ty",
    "ctcp",
    "ngan hang",
    "quy",
    "tmcp",
    "tnhh",
}


def normalize_vietnamese_person_name(value: str) -> str:
    """Normalize a Vietnamese person name while keeping real name tokens."""
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r"^(ông|ong|bà|ba|mr\.?|mrs\.?|ms\.?)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-")
    return text.lower()


def normalize_vietnamese_person_name_ascii(value: str) -> str:
    text = normalize_vietnamese_person_name(value)
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    text = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _person_tokens(value: str) -> list[str]:
    return [token for token in normalize_vietnamese_person_name_ascii(value).split() if token]


def _is_organization_holder(value: Any) -> bool:
    text = normalize_vietnamese_person_name_ascii(str(value or ""))
    if not text:
        return False
    return any(marker in text for marker in ORGANIZATION_HOLDER_MARKERS)


class StockDataService:
    """Chuẩn hóa dữ liệu stock từ direct payload hoặc Backend API."""

    def unwrap_backend_response(self, payload: Any) -> Any:
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def normalize_stock_detail(self, payload: Any) -> dict[str, Any]:
        data = self.unwrap_backend_response(payload)
        if not isinstance(data, dict):
            data = {"raw": data}
        return data

    def normalize_analysis_data(self, payload: Any) -> dict[str, Any]:
        data = self.normalize_stock_detail(payload)
        latest_market = self._first_dict(data, "latest_market", "latestMarket", "latest_price", "latestPrice")
        price_history = self._first_list(data, "price_history", "priceHistory", "prices", "chart", "candles")
        financials_raw = data.get("financials") or {}
        financial_periods: list[dict[str, Any]] = []
        if isinstance(financials_raw, dict):
            financial_periods = self._first_list(financials_raw, "periods", "items")
        elif isinstance(financials_raw, list):
            financial_periods = [item for item in financials_raw if isinstance(item, dict)]
        financial_periods = self.sanitize_financial_periods(financial_periods)

        financials = dict(financials_raw) if isinstance(financials_raw, dict) else {}
        financials["periods"] = financial_periods

        valid_financial_periods = self.valid_financial_periods(financial_periods)
        data_quality = self._normalize_data_quality(self._first_dict(data, "data_quality", "dataQuality"), valid_financial_periods, price_history)
        suspicious_notes = self.financial_suspicious_notes(financial_periods)
        if suspicious_notes:
            warnings = list(data_quality.get("warnings") or [])
            warnings.extend(suspicious_notes)
            data_quality["warnings"] = self._dedupe_strings(warnings)
        if financial_periods and not valid_financial_periods:
            warnings = list(data_quality.get("warnings") or [])
            warnings.append("Dữ liệu tài chính hiện chỉ nhận diện được kỳ báo cáo nhưng chưa đủ chỉ tiêu định lượng.")
            data_quality["warnings"] = self._dedupe_strings(warnings)
        source_statuses = data.get("source_statuses") or data.get("sourceStatuses") or []
        if not isinstance(source_statuses, list):
            source_statuses = []
        source_success = data.get("_source_success") or data.get("source_success") or data.get("sourceSuccess") or {}
        if not isinstance(source_success, dict):
            source_success = {}

        company_overview = self._first_dict(data, "company_overview", "companyOverview", "business_overview", "businessOverview")
        company_overview, leadership_ownership_merge = self.enrich_leadership_with_ownership(company_overview)

        return {
            "symbol": data.get("symbol") or self._nested_value(data, "stock", "symbol"),
            "exchange": data.get("exchange") or data.get("scope_exchange") or data.get("market_code") or self._nested_value(data, "stock", "market_code"),
            "company": data.get("company") or data.get("company_name") or data.get("name") or data.get("organName") or self.extract_company(data),
            "latest_market": latest_market,
            "latest_price": latest_market,
            "price_history": price_history,
            "priceHistory": price_history,
            "financials": financials,
            "financial_balance": self.sanitize_financial_balance(
                self._first_dict(data, "financial_balance", "financialBalance"),
                financial_periods,
            ),
            "hose_market_context": self._first_dict(data, "hose_market_context", "hoseMarketContext", "market_overview", "marketOverview"),
            "market_general_context": self._first_dict(data, "market_general_context", "marketGeneralContext"),
            "industry_peer_context": self._first_dict(data, "industry_peer_context", "industryPeerContext"),
            "same_industry_recommendation": self._first_dict(data, "same_industry_recommendation", "sameIndustryRecommendation"),
            "company_overview": company_overview,
            "data_quality": data_quality,
            "source_statuses": source_statuses,
            "_leadership_ownership_merge": leadership_ownership_merge,
            "_source_success": source_success,
            "raw": data,
        }

    def normalize_stock_chart(self, payload: Any) -> list[dict[str, Any]]:
        data = self.unwrap_backend_response(payload)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("items", "prices", "chart", "candles", "price_history", "priceHistory"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def merge_chart_history(self, stock_detail: dict[str, Any], chart_payload: Any) -> dict[str, Any]:
        history = self.normalize_stock_chart(chart_payload)
        if not history:
            return stock_detail
        merged = dict(stock_detail)
        merged["price_history"] = history
        merged["priceHistory"] = history
        return merged

    def merge_financial_fallback(self, stock_detail: dict[str, Any], fallback_payload: dict[str, Any]) -> dict[str, Any]:
        periods = fallback_payload.get("periods") if isinstance(fallback_payload, dict) else []
        if not isinstance(periods, list) or not periods:
            merged = dict(stock_detail)
            merged["_financial_fallback"] = fallback_payload
            return merged
        periods = self.sanitize_financial_periods(periods)
        valid_periods = self.valid_financial_periods(periods)
        if not valid_periods:
            merged = dict(stock_detail)
            merged["_financial_fallback"] = fallback_payload
            data_quality = dict(self._dict(merged.get("data_quality")))
            warnings = list(data_quality.get("warnings") or [])
            warnings.append("Dữ liệu tài chính công khai chỉ nhận diện được kỳ báo cáo nhưng chưa đủ số liệu định lượng.")
            data_quality["warnings"] = self._dedupe_strings(warnings)
            data_quality["financials_loaded"] = False
            data_quality["financial_periods_count"] = 0
            merged["data_quality"] = data_quality
            return merged

        merged = self.normalize_analysis_data(stock_detail)
        existing_periods = self._first_list(self._dict(merged.get("financials")), "periods")
        if self.full_financial_periods(existing_periods):
            merged["_financial_fallback"] = fallback_payload
            return merged

        ratio_only = bool(fallback_payload.get("financial_ratios_only")) or bool(valid_periods and not self.full_financial_periods(valid_periods))
        financials = dict(self._dict(merged.get("financials")))
        financials["periods"] = valid_periods
        financials["source"] = fallback_payload.get("source")
        financials["source_url"] = fallback_payload.get("source_url")
        financials["unit"] = fallback_payload.get("unit")
        financials["updated_at"] = fallback_payload.get("fetched_at")
        merged["financials"] = financials

        if not merged.get("financial_balance") and financials["periods"]:
            latest = financials["periods"][0]
            balance_keys = (
                "period",
                "total_assets",
                "total_liabilities",
                "equity",
                "current_assets",
                "current_liabilities",
                "cash",
                "inventory",
                "short_term_investments",
                "short_term_receivables",
                "other_current_assets",
                "long_term_assets",
                "fixed_assets",
                "investment_properties",
                "long_term_investments",
                "long_term_liabilities",
                "total_capital",
                "owner_capital",
                "share_premium",
                "retained_earnings",
                "debt_to_assets",
                "debt_to_equity",
                "current_ratio",
                "interest_coverage",
                "pe",
                "pb",
                "roe",
                "roa",
                "eps_ttm",
                "bvps",
                "gross_margin",
                "net_margin",
                "net_interest_income",
                "interest_income",
                "interest_expense",
                "net_fee_income",
                "operating_expense",
                "pre_provision_operating_profit",
                "credit_provision_expense",
                "customer_loans",
                "customer_deposits",
                "deposit_at_state_bank",
                "interbank_assets",
                "loan_loss_reserve",
                "investment_securities",
                "valuable_papers_issued",
                "npl_ratio",
                "loan_loss_coverage",
                "nim",
                "casa_ratio",
            )
            merged["financial_balance"] = {key: latest.get(key) for key in balance_keys if latest.get(key) is not None}

        data_quality = dict(self._dict(merged.get("data_quality")))
        warnings = list(data_quality.get("warnings") or [])
        source_name = str(fallback_payload.get("source") or "nguồn công khai")
        warnings.append(f"Báo cáo đã bổ sung dữ liệu tài chính từ {source_name} để đối chiếu với dữ liệu nội bộ.")
        warnings.extend(fallback_payload.get("warnings") or [])
        warnings.extend(self.financial_suspicious_notes(financials["periods"]))
        if ratio_only:
            data_quality["financials_loaded"] = False
            data_quality["financial_periods_count"] = 0
            data_quality["financial_ratios_loaded"] = True
            data_quality["financial_ratio_periods_count"] = len(financials["periods"])
            warnings.append("Nguồn công khai hiện mới đủ nhóm chỉ số tài chính, chưa đủ bộ BCTC đầy đủ.")
        else:
            data_quality["financials_loaded"] = True
            data_quality["financial_periods_count"] = len(financials["periods"])
            data_quality["financial_ratios_loaded"] = any(self.is_ratio_financial_period(period) for period in financials["periods"])
            data_quality["financial_ratio_periods_count"] = len(self.ratio_financial_periods(financials["periods"]))
        data_quality["warnings"] = self._dedupe_strings(warnings)
        units = dict(data_quality.get("units") if isinstance(data_quality.get("units"), dict) else {})
        if fallback_payload.get("unit"):
            units["financial_statement_money_fields"] = fallback_payload.get("unit")
        if units:
            data_quality["units"] = units
        missing = data_quality.get("missing_fields") or []
        if isinstance(missing, list):
            data_quality["missing_fields"] = [item for item in missing if item not in {"financials.periods", "financials", "bctc"}]
        merged["data_quality"] = data_quality
        merged["_financial_fallback"] = fallback_payload
        return merged

    def merge_company_fallback(self, stock_detail: dict[str, Any], fallback_payload: dict[str, Any]) -> dict[str, Any]:
        merged = self.normalize_analysis_data(stock_detail)
        merged["_company_fallback"] = fallback_payload
        if not isinstance(fallback_payload, dict) or fallback_payload.get("status") in {"disabled", "failed"}:
            return merged

        overview = dict(self._dict(merged.get("company_overview")))
        for source_key, target_key in (
            ("company_name", "company_name"),
            ("exchange", "exchange"),
            ("industry_level_1", "industry_level_1"),
            ("industry_level_2", "industry_level_2"),
            ("industry_level_3", "industry_level_3"),
            ("industry", "industry"),
            ("sector", "sector"),
            ("business_overview", "business_overview"),
            ("source", "source"),
            ("source_url", "source_url"),
            ("confidence", "confidence"),
            ("fetched_at", "fetched_at"),
        ):
            value = fallback_payload.get(source_key)
            if value not in (None, "", {}, []):
                overview.setdefault(target_key, value)
        if str(fallback_payload.get("source") or "").strip().lower() in {"cafef", "cafef thông tin doanh nghiệp"}:
            overview.setdefault("source_display", "CafeF thông tin doanh nghiệp")
        for list_key in ("leadership", "ownership"):
            value = fallback_payload.get(list_key)
            if isinstance(value, list) and value:
                overview.setdefault(list_key, value)
        overview, leadership_ownership_merge = self.enrich_leadership_with_ownership(overview)
        merged["_leadership_ownership_merge"] = leadership_ownership_merge
        if overview:
            merged["company_overview"] = overview

        if fallback_payload.get("company_name") and not merged.get("company"):
            merged["company"] = fallback_payload.get("company_name")

        peer_context = dict(self._dict(merged.get("industry_peer_context")))
        industry = dict(self._dict(peer_context.get("industry")))
        sector = fallback_payload.get("industry_level_1") or fallback_payload.get("sector")
        industry_group = fallback_payload.get("industry_level_2")
        industry_detail = fallback_payload.get("industry_level_3")
        legacy_industry = fallback_payload.get("industry")
        if sector:
            industry.setdefault("sector", sector)
            industry.setdefault("industry_level_1", sector)
        if industry_group:
            industry.setdefault("industry_group", industry_group)
            industry.setdefault("industry_level_2", industry_group)
        if industry_detail:
            industry.setdefault("industry", industry_detail)
            industry.setdefault("industry_level_3", industry_detail)
        elif legacy_industry:
            industry.setdefault("industry", legacy_industry)
        if industry:
            industry.setdefault("source", fallback_payload.get("source"))
            industry.setdefault("source_url", fallback_payload.get("source_url"))
            peer_context["industry"] = industry
            merged["industry_peer_context"] = peer_context

        data_quality = dict(self._dict(merged.get("data_quality")))
        warnings = list(data_quality.get("warnings") or [])
        if overview:
            warnings.append("Báo cáo đã đối chiếu thông tin doanh nghiệp từ CafeF.")
        warnings.extend(fallback_payload.get("warnings") or [])
        data_quality["warnings"] = self._dedupe_strings(warnings)
        merged["data_quality"] = data_quality
        return merged

    @classmethod
    def enrich_leadership_with_ownership(cls, company_overview: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        overview = dict(company_overview) if isinstance(company_overview, dict) else {}
        leadership = [dict(item) for item in cls._list_dicts(overview.get("leadership"))]
        ownership = [dict(item) for item in cls._list_dicts(overview.get("ownership"))]
        debug = {
            "leadership_rows": leadership,
            "ownership_rows": ownership,
            "matches": [],
            "unmatched_leadership": [],
            "unmatched_ownership": [],
        }
        if not leadership:
            return overview, debug

        matched_ownership_indexes: set[int] = set()
        enriched: list[dict[str, Any]] = []
        for leader in leadership:
            leader_name = str(cls._first_non_empty(leader, "name", "full_name", "person") or "")
            match = cls._find_ownership_match(leader_name, ownership)
            if match is None:
                leader.setdefault("shares", None)
                leader.setdefault("ownership_percent", None)
                leader.setdefault("ownership_match", "not_found")
                leader.setdefault("ownership_note", "Chưa xác minh")
                debug["unmatched_leadership"].append({"leadership_name": leader_name})
                enriched.append(leader)
                continue

            ownership_index, holder, method, confidence = match
            matched_ownership_indexes.add(ownership_index)
            holder_name = str(cls._first_non_empty(holder, "holder", "name", "shareholder") or "")
            shares = cls._first_non_empty(holder, "shares", "share_count", "shareholding", "volume")
            ownership_percent = cls._first_non_empty(holder, "ownership_percent", "ratio", "percent", "percentage")
            if cls._is_missing(leader.get("shares")) and not cls._is_missing(shares):
                leader["shares"] = shares
            else:
                leader.setdefault("shares", None)
            if cls._is_missing(leader.get("ownership_percent")) and not cls._is_missing(ownership_percent):
                leader["ownership_percent"] = ownership_percent
            else:
                leader.setdefault("ownership_percent", None)
            source = cls._ownership_source_label(holder)
            leader["ownership_source"] = source
            leader["ownership_match"] = method
            leader["ownership_match_confidence"] = confidence
            leader["ownership_note"] = "Đối chiếu từ bảng cổ đông lớn CafeF" if "CafeF" in source else f"Đối chiếu từ {source}"
            debug["matches"].append(
                {
                    "leadership_name": leader_name,
                    "ownership_holder": holder_name,
                    "normalized_name": normalize_vietnamese_person_name(leader_name),
                    "match_confidence": confidence,
                    "shares": shares,
                    "ownership_percent": ownership_percent,
                }
            )
            enriched.append(leader)

        for index, holder in enumerate(ownership):
            if index not in matched_ownership_indexes:
                debug["unmatched_ownership"].append(
                    {"ownership_holder": cls._first_non_empty(holder, "holder", "name", "shareholder")}
                )

        overview["leadership"] = enriched
        return overview, debug

    @classmethod
    def _find_ownership_match(
        cls,
        leader_name: str,
        ownership: list[dict[str, Any]],
    ) -> tuple[int, dict[str, Any], str, float] | None:
        leader_norm = normalize_vietnamese_person_name(leader_name)
        leader_ascii = normalize_vietnamese_person_name_ascii(leader_name)
        leader_tokens = leader_ascii.split()
        if len(leader_tokens) < 2:
            return None
        for index, holder in enumerate(ownership):
            holder_name = str(cls._first_non_empty(holder, "holder", "name", "shareholder") or "")
            if _is_organization_holder(holder_name):
                continue
            holder_norm = normalize_vietnamese_person_name(holder_name)
            holder_ascii = normalize_vietnamese_person_name_ascii(holder_name)
            holder_tokens = holder_ascii.split()
            if len(holder_tokens) < 2:
                continue
            if leader_norm == holder_norm:
                return index, holder, "matched_by_normalized_name", 0.95
            if leader_ascii and leader_ascii == holder_ascii:
                return index, holder, "matched_by_accent_insensitive_name", 0.93
            if cls._safe_token_match(leader_tokens, holder_tokens):
                return index, holder, "matched_by_safe_token_set", 0.85
        return None

    @staticmethod
    def _safe_token_match(leader_tokens: list[str], holder_tokens: list[str]) -> bool:
        if len(leader_tokens) < 3 or len(holder_tokens) < 3:
            return False
        leader_set = set(leader_tokens)
        holder_set = set(holder_tokens)
        if leader_set == holder_set:
            return True
        if holder_set.issubset(leader_set) and len(leader_set - holder_set) <= 1:
            return True
        if leader_set.issubset(holder_set) and len(holder_set - leader_set) <= 1:
            return True
        return False

    @staticmethod
    def _ownership_source_label(holder: dict[str, Any]) -> str:
        source = str(holder.get("source_display") or holder.get("source") or "CafeF cổ đông lớn").strip()
        if source.lower() in {"cafef", "cafef thông tin doanh nghiệp"}:
            return "CafeF cổ đông lớn"
        return source or "CafeF cổ đông lớn"

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return value in (None, "", {}, [])

    @staticmethod
    def _first_non_empty(data: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in data and data[key] not in (None, "", {}, []):
                return data[key]
        return None

    @staticmethod
    def _list_dicts(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def merge_peer_fallback(self, stock_detail: dict[str, Any], fallback_payload: dict[str, Any], *, symbol: str | None = None, top_n: int = 5) -> dict[str, Any]:
        peers = fallback_payload.get("peers") if isinstance(fallback_payload, dict) else []
        valid_peers = self.valid_peers(peers if isinstance(peers, list) else [], symbol=symbol)
        merged = self.normalize_analysis_data(stock_detail)
        merged["_peer_fallback"] = fallback_payload
        fallback_industry = fallback_payload.get("industry") if isinstance(fallback_payload, dict) else {}
        fallback_industry = fallback_industry if isinstance(fallback_industry, dict) else {}
        if not valid_peers and fallback_industry:
            peer_context = dict(self._dict(merged.get("industry_peer_context")))
            industry = dict(self._dict(peer_context.get("industry")))
            for key, value in fallback_industry.items():
                if value not in (None, "", {}, []):
                    industry.setdefault(key, value)
            industry.setdefault("source", fallback_payload.get("source"))
            industry.setdefault("source_url", fallback_payload.get("source_url"))
            peer_context["industry"] = industry
            peer_context.setdefault("source", fallback_payload.get("source"))
            peer_context.setdefault("source_url", fallback_payload.get("source_url"))
            merged["industry_peer_context"] = peer_context
        if not valid_peers:
            data_quality = dict(self._dict(merged.get("data_quality")))
            warnings = list(data_quality.get("warnings") or [])
            if fallback_industry:
                warnings.append("Dữ liệu ngành đã được đối chiếu, nhưng peer định lượng vẫn chưa đủ để so sánh.")
            else:
                warnings.append("Dữ liệu peer công khai chưa đủ để lập bảng so sánh định lượng.")
            data_quality["warnings"] = self._dedupe_strings(warnings)
            data_quality["peer_context_loaded"] = bool(self._first_list(self._dict(merged.get("industry_peer_context")), "peers"))
            merged["data_quality"] = data_quality
            return merged

        peer_context = dict(self._dict(merged.get("industry_peer_context")))
        existing_peers = self._first_list(peer_context, "peers")
        if not self.valid_peers(existing_peers, symbol=symbol):
            peer_context["peers"] = valid_peers
            industry = dict(self._dict(peer_context.get("industry")))
            if fallback_industry:
                for key, value in fallback_industry.items():
                    if value not in (None, "", {}, []):
                        industry.setdefault(key, value)
            elif not industry:
                industry = {"industry": "Cùng ngành theo Vietstock Finance", "source": fallback_payload.get("source")}
            industry.setdefault("source", fallback_payload.get("source"))
            industry.setdefault("source_url", fallback_payload.get("source_url"))
            peer_context["industry"] = industry
            peer_context["source"] = fallback_payload.get("source")
            peer_context["source_url"] = fallback_payload.get("source_url")
            merged["industry_peer_context"] = peer_context

        recommendation = dict(self._dict(merged.get("same_industry_recommendation")))
        existing_candidates = recommendation.get("candidates") if isinstance(recommendation.get("candidates"), list) else []
        if not existing_candidates:
            recommendation["method"] = "So sánh cùng ngành từ Vietstock Finance"
            recommendation["candidates"] = [self._peer_to_candidate(peer) for peer in self._rank_peers(valid_peers)[: max(1, top_n)]]
            merged["same_industry_recommendation"] = recommendation

        data_quality = dict(self._dict(merged.get("data_quality")))
        warnings = list(data_quality.get("warnings") or [])
        warnings.append("Báo cáo đã bổ sung dữ liệu peer cùng ngành từ Vietstock Finance để đối chiếu tương quan.")
        data_quality["warnings"] = self._dedupe_strings(warnings)
        data_quality["peer_context_loaded"] = True
        merged["data_quality"] = data_quality
        return merged

    @classmethod
    def is_valid_financial_period(cls, period: dict[str, Any]) -> bool:
        if not isinstance(period, dict):
            return False
        meaningful = 0
        for key in FINANCIAL_METRIC_FIELDS:
            value = period.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                meaningful += 1
        return meaningful >= 3

    @classmethod
    def valid_financial_periods(cls, periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [period for period in periods if cls.is_valid_financial_period(period)]

    @classmethod
    def sanitize_financial_periods(cls, periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(periods, list):
            return []
        return [cls.sanitize_financial_period(period) for period in periods if isinstance(period, dict)]

    @classmethod
    def sanitize_financial_period(cls, period: dict[str, Any]) -> dict[str, Any]:
        clean = dict(period)
        notes: list[str] = []
        if not cls.looks_like_bank_period(clean):
            return clean

        total_assets = cls._numeric(clean.get("total_assets"))
        customer_loans = cls._numeric(clean.get("customer_loans"))
        customer_deposits = cls._numeric(clean.get("customer_deposits"))
        equity = cls._numeric(clean.get("equity"))
        roa = cls._numeric(clean.get("roa"))
        roe = cls._numeric(clean.get("roe"))

        if total_assets is not None and 0 < total_assets < 1000:
            clean.pop("total_assets", None)
            notes.append("Tổng tài sản ngân hàng bị loại khỏi phần định lượng vì giá trị quá nhỏ, có khả năng là chỉ số tỷ suất bị map nhầm.")
            total_assets = None
        if total_assets and customer_loans and customer_loans > total_assets * 1.2:
            clean.pop("customer_loans", None)
            notes.append("Cho vay khách hàng bị đánh dấu chưa xác minh vì lớn bất thường so với tổng tài sản.")
            customer_loans = None
        if total_assets and customer_deposits and customer_deposits > total_assets * 1.2:
            clean.pop("customer_deposits", None)
            notes.append("Tiền gửi khách hàng bị đánh dấu chưa xác minh vì lớn bất thường so với tổng tài sản.")
            customer_deposits = None
        if total_assets and equity and equity > total_assets:
            clean.pop("equity", None)
            notes.append("Vốn chủ sở hữu bị loại khỏi phần định lượng vì lớn hơn tổng tài sản.")
            equity = None
        balance_anchor = max(value for value in (customer_loans, customer_deposits, total_assets) if value is not None) if any(
            value is not None for value in (customer_loans, customer_deposits, total_assets)
        ) else None
        if balance_anchor and equity and equity > balance_anchor * 0.5:
            clean.pop("equity", None)
            notes.append("Vốn chủ sở hữu bị đánh dấu chưa xác minh vì tỷ trọng bất thường so với quy mô tài sản/huy động.")
        if roa is not None and abs(roa) > 20:
            clean.pop("roa", None)
            notes.append("ROA/ROAA bị đánh dấu chưa xác minh vì vượt ngưỡng hợp lý.")
        if roe is not None and abs(roe) > 50:
            clean.pop("roe", None)
            notes.append("ROE bị đánh dấu chưa xác minh vì vượt ngưỡng hợp lý.")
        if notes:
            clean["_suspicious_financial_fields"] = cls._dedupe_note_list(
                [*cls._as_note_list(clean.get("_suspicious_financial_fields")), *notes]
            )
        return clean

    @classmethod
    def sanitize_financial_balance(cls, balance: dict[str, Any], periods: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not isinstance(balance, dict) or not balance:
            return {}
        if cls.looks_like_bank_period(balance):
            return cls.sanitize_financial_period(balance)
        period_list = periods if isinstance(periods, list) else []
        if any(cls.looks_like_bank_period(period) for period in period_list):
            return cls.sanitize_financial_period(balance)
        return balance

    @classmethod
    def financial_suspicious_notes(cls, periods: list[dict[str, Any]]) -> list[str]:
        notes: list[str] = []
        for period in periods or []:
            if isinstance(period, dict):
                notes.extend(cls._as_note_list(period.get("_suspicious_financial_fields")))
        return cls._dedupe_note_list(notes)

    @classmethod
    def looks_like_bank_period(cls, period: dict[str, Any]) -> bool:
        if not isinstance(period, dict):
            return False
        return any(period.get(key) not in (None, "") for key in BANK_INDICATOR_FIELDS)

    @classmethod
    def is_full_financial_period(cls, period: dict[str, Any]) -> bool:
        if not isinstance(period, dict):
            return False
        meaningful = sum(
            1
            for key in FULL_BCTC_METRIC_FIELDS
            if isinstance(period.get(key), (int, float)) and not isinstance(period.get(key), bool)
        )
        return meaningful >= 3

    @classmethod
    def full_financial_periods(cls, periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [period for period in periods if cls.is_full_financial_period(period)]

    @classmethod
    def is_ratio_financial_period(cls, period: dict[str, Any]) -> bool:
        if not isinstance(period, dict):
            return False
        meaningful = sum(
            1
            for key in FINANCIAL_RATIO_FIELDS
            if isinstance(period.get(key), (int, float)) and not isinstance(period.get(key), bool)
        )
        return meaningful >= 2

    @classmethod
    def ratio_financial_periods(cls, periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [period for period in periods if cls.is_ratio_financial_period(period)]

    @staticmethod
    def _numeric(value: Any) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return None

    @staticmethod
    def _as_note_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if value:
            return [str(value).strip()]
        return []

    @staticmethod
    def _dedupe_note_list(values: list[Any]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = str(value).strip()
            if clean and clean not in seen:
                result.append(clean)
                seen.add(clean)
        return result

    @classmethod
    def is_valid_peer(cls, peer: dict[str, Any], *, symbol: str | None = None) -> bool:
        if not isinstance(peer, dict):
            return False
        peer_symbol = str(peer.get("symbol") or peer.get("ticker") or "").strip().upper()
        if not peer_symbol:
            return False
        if symbol and peer_symbol == str(symbol).strip().upper():
            return False
        if not (peer.get("source") or peer.get("source_url")):
            return False
        useful_metrics = 0
        for key in cls.peer_metric_fields():
            if isinstance(peer.get(key), (int, float)) and not isinstance(peer.get(key), bool):
                useful_metrics += 1
        if useful_metrics >= 2:
            return True
        evidence = str(peer.get("verified_row_evidence") or "")
        return bool(peer.get("company") or peer.get("company_name")) and evidence in {"stock_link", "table", "json"}

    @classmethod
    def valid_peers(cls, peers: list[dict[str, Any]], *, symbol: str | None = None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for peer in peers:
            peer_symbol = str((peer or {}).get("symbol") or (peer or {}).get("ticker") or "").strip().upper()
            if peer_symbol in seen:
                continue
            if cls.is_valid_peer(peer, symbol=symbol):
                normalized = dict(peer)
                normalized["symbol"] = peer_symbol
                result.append(normalized)
                seen.add(peer_symbol)
        return result

    def extract_company(self, stock_detail: dict[str, Any]) -> str | None:
        stock = stock_detail.get("stock") if isinstance(stock_detail.get("stock"), dict) else stock_detail
        return stock.get("company") or stock.get("company_name") or stock.get("name") or stock.get("organName")

    def _normalize_data_quality(
        self,
        data_quality: dict[str, Any],
        financial_periods: list[dict[str, Any]],
        price_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        periods = financial_periods if isinstance(financial_periods, list) else []
        missing_fields = data_quality.get("missing_fields") or data_quality.get("missingFields") or []
        warnings = data_quality.get("warnings") or []
        return {
            "financials_loaded": self._bool_value(data_quality, "financials_loaded", "financialsLoaded", fallback=bool(periods)),
            "financial_periods_count": self._int_value(data_quality, "financial_periods_count", "financialPeriodsCount", fallback=len(periods)),
            "financial_ratios_loaded": self._bool_value(data_quality, "financial_ratios_loaded", "financialRatiosLoaded", fallback=bool(self.ratio_financial_periods(periods))),
            "financial_ratio_periods_count": self._int_value(data_quality, "financial_ratio_periods_count", "financialRatioPeriodsCount", fallback=len(self.ratio_financial_periods(periods))),
            "price_history_points": self._int_value(data_quality, "price_history_points", "priceHistoryPoints", fallback=len(price_history)),
            "market_context_loaded": self._bool_value(data_quality, "market_context_loaded", "marketContextLoaded", fallback=False),
            "peer_context_loaded": self._bool_value(data_quality, "peer_context_loaded", "peerContextLoaded", fallback=False),
            "missing_fields": missing_fields if isinstance(missing_fields, list) else [],
            "warnings": warnings if isinstance(warnings, list) else [],
            "units": data_quality.get("units") if isinstance(data_quality.get("units"), dict) else {},
        }

    def _first_dict(self, data: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict):
                return value
        return {}

    def _first_list(self, data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _nested_value(self, data: dict[str, Any], parent: str, key: str) -> Any:
        parent_value = data.get(parent)
        if isinstance(parent_value, dict):
            return parent_value.get(key)
        return None

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _dedupe_strings(self, values: list[Any]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = str(value).strip()
            if clean and clean not in seen:
                result.append(clean)
                seen.add(clean)
        return result

    def _peer_to_candidate(self, peer: dict[str, Any]) -> dict[str, Any]:
        missing_metrics = self._peer_missing_metrics(peer)
        available_data = self._peer_available_data(peer)
        has_quant = len(available_data) >= 3
        signal = str(peer.get("buy_sell_signal") or "").lower()
        rsi = peer.get("rsi_14")
        label = "Đáng theo dõi" if has_quant else "Thiếu dữ liệu"
        if "bán" in signal or (isinstance(rsi, (int, float)) and rsi < 30):
            label = "Rủi ro cao"
        elif not peer.get("fundamental_rating") and not peer.get("basic_score"):
            label = "Cần chờ xác nhận"
        source_items = peer.get("enrichment_sources") if isinstance(peer.get("enrichment_sources"), list) else []
        sources = [str(item.get("source")) for item in source_items if isinstance(item, dict) and item.get("source")]
        if peer.get("source"):
            sources.insert(0, str(peer.get("source")))
        reason = peer.get("same_industry_reason") or "Được ghi nhận trong bảng so sánh cùng ngành của Vietstock Finance."
        strengths = self._peer_strengths(peer, available_data)
        risk = peer.get("data_note") or peer.get("buy_sell_signal") or "Cần đối chiếu thêm khác biệt mô hình kinh doanh, quy mô và chất lượng tài sản trước khi so sánh."
        return {
            "symbol": peer.get("symbol"),
            "ticker": peer.get("symbol"),
            "company": peer.get("company") or peer.get("company_name"),
            "label": label,
            "reason_to_watch": reason,
            "why_watch": reason,
            "supporting_data": {
                "close_price": peer.get("close_price") or peer.get("price"),
                "change_1d_percent": peer.get("change_1d_percent"),
                "matched_value_billion": peer.get("matched_value_billion"),
                "market_cap_billion": peer.get("market_cap_billion") or peer.get("market_cap"),
                "eps_4q": peer.get("eps_4q"),
                "pe_basic": peer.get("pe_basic") or peer.get("pe"),
                "rsi_14": peer.get("rsi_14"),
                "basic_score": peer.get("basic_score"),
                "fundamental_rating": peer.get("fundamental_rating"),
                "pb": peer.get("pb"),
                "roe": peer.get("roe"),
            },
            "strengths": strengths,
            "strength_items": [item.strip() for item in strengths.split(";") if item.strip()],
            "risks": [risk],
            "key_risk": risk,
            "missing_data": ", ".join(missing_metrics) if missing_metrics else "",
            "missing_data_items": missing_metrics,
            "available_data": ", ".join(available_data) if available_data else "Chưa có chỉ tiêu định lượng đáng tin cậy",
            "available_data_items": available_data,
            "source": peer.get("source"),
            "source_url": peer.get("source_url"),
            "sources": self._dedupe_strings(sources),
            "confidence": peer.get("confidence"),
        }

    @classmethod
    def peer_metric_fields(cls) -> tuple[str, ...]:
        return (
            "price",
            "close_price",
            "change_1d_percent",
            "matched_volume",
            "matched_value_billion",
            "market_cap",
            "market_cap_billion",
            "eps_4q",
            "pe",
            "pe_basic",
            "pb",
            "roe",
            "revenue",
            "profit_after_tax",
            "net_margin",
            "momentum_1m",
            "liquidity",
            "macd",
            "rsi_14",
            "basic_score",
        )

    def _rank_peers(self, peers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def score(peer: dict[str, Any]) -> tuple[float, float, float, float, float]:
            rating = str(peer.get("fundamental_rating") or "").upper()
            rating_score = {"A": 3, "B": 2, "C": 1}.get(rating[:1], 0)
            pe = peer.get("pe_basic") or peer.get("pe")
            pe_score = 1.0 if isinstance(pe, (int, float)) and 0 < pe <= 18 else 0.0
            value = peer.get("matched_value_billion") or peer.get("liquidity") or 0
            rsi = peer.get("rsi_14")
            rsi_score = 1.0 if isinstance(rsi, (int, float)) and 30 <= rsi <= 70 else 0.0
            completeness = len(self._peer_available_data(peer))
            return (float(completeness), rating_score, pe_score, float(value or 0), rsi_score)

        return sorted(peers, key=score, reverse=True)

    def _peer_missing_metrics(self, peer: dict[str, Any]) -> list[str]:
        checks = (
            ("Giá", peer.get("close_price") or peer.get("price")),
            ("Vốn hóa", peer.get("market_cap_billion") or peer.get("market_cap")),
            ("EPS 4Q", peer.get("eps_4q")),
            ("P/E", peer.get("pe_basic") or peer.get("pe")),
            ("P/B", peer.get("pb")),
            ("ROE", peer.get("roe")),
        )
        existing = peer.get("missing_metrics")
        if isinstance(existing, list) and existing:
            return [str(item) for item in existing if str(item).strip()]
        return [label for label, value in checks if value in (None, "", [], {})]

    def _peer_available_data(self, peer: dict[str, Any]) -> list[str]:
        checks = (
            ("Giá", peer.get("close_price") or peer.get("price")),
            ("% 1D", peer.get("change_1d_percent")),
            ("GT giao dịch", peer.get("matched_value_billion") or peer.get("liquidity")),
            ("Vốn hóa", peer.get("market_cap_billion") or peer.get("market_cap")),
            ("EPS 4Q", peer.get("eps_4q")),
            ("P/E", peer.get("pe_basic") or peer.get("pe")),
            ("P/B", peer.get("pb")),
            ("ROE", peer.get("roe")),
            ("Tín hiệu", peer.get("buy_sell_signal")),
        )
        return [label for label, value in checks if value not in (None, "", [], {})]

    def _peer_strengths(self, peer: dict[str, Any], available_data: list[str]) -> str:
        parts: list[str] = []
        if peer.get("industry") or peer.get("same_industry_reason"):
            parts.append("cùng nhóm ngành theo nguồn peer")
        if peer.get("matched_value_billion") or peer.get("liquidity"):
            parts.append("có dữ liệu thanh khoản")
        if peer.get("pe_basic") or peer.get("pe") or peer.get("pb") or peer.get("roe"):
            parts.append("có chỉ tiêu định giá/sinh lời")
        if not parts and available_data:
            parts.append("có một số dữ liệu để đối chiếu sơ bộ")
        return "; ".join(parts) if parts else "Cần bổ sung dữ liệu trước khi so sánh sâu."

    def _bool_value(self, data: dict[str, Any], *keys: str, fallback: bool = False) -> bool:
        for key in keys:
            value = data.get(key)
            if isinstance(value, bool):
                return value
        return fallback

    def _int_value(self, data: dict[str, Any], *keys: str, fallback: int = 0) -> int:
        for key in keys:
            value = data.get(key)
            if isinstance(value, int):
                return value
        return fallback
