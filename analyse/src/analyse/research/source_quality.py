from __future__ import annotations

from datetime import datetime, timezone
import re

from analyse.research.base import normalize_domain
from analyse.utils.symbol_utils import normalize_symbol


class SourceQualityScorer:
    """Score evidence reliability, relevance and freshness."""

    OFFICIAL_DOMAINS = {"hsx.vn", "hnx.vn", "ssc.gov.vn"}
    STRUCTURED_DOMAINS = {"finance.vietstock.vn", "vietstock.vn", "cafef.vn"}
    REPUTABLE_NEWS = {
        "tinnhanhchungkhoan.vn",
        "vneconomy.vn",
        "bnews.vn",
        "vietnambiz.vn",
        "ndh.vn",
        "fireant.vn",
        "stockbiz.vn",
    }

    def reliability_score(self, *, source_name: str, source_type: str, url: str | None = None) -> float:
        domain = normalize_domain(url)
        source_key = str(source_name or "").strip().lower()
        if source_type == "backend" or domain in self.OFFICIAL_DOMAINS:
            return 1.0
        if any(name in source_key for name in ("hose", "hnx", "ủy ban chứng khoán", "ssc")):
            return 1.0
        if source_type in {"structured_financial", "company_profile", "peer_data"} or domain in self.STRUCTURED_DOMAINS:
            return 0.9
        if any(name in source_key for name in ("vietstock", "cafef")):
            return 0.85
        if source_type == "official_disclosure":
            return 1.0
        if source_type == "news":
            if domain in self.REPUTABLE_NEWS:
                return 0.8
            if domain in {"vietstock.vn", "cafef.vn"}:
                return 0.85
            if any(
                name in source_key
                for name in (
                    "tin nhanh chứng khoán",
                    "vneconomy",
                    "bnews",
                    "vietnambiz",
                    "ndh",
                    "fireant",
                    "stockbiz",
                    "vietnam biz",
                )
            ):
                return 0.78
            return 0.55
        if source_type == "model_inference":
            return 0.5
        return 0.6

    def freshness_score(self, published_at: datetime | None, *, source_type: str) -> float:
        if source_type in {"company_profile", "structured_financial", "backend", "peer_data"}:
            return 0.85 if published_at is None else self._age_score(published_at, long_lived=True)
        if published_at is None:
            return 0.45
        return self._age_score(published_at, long_lived=False)

    def relevance_score(
        self,
        *,
        title: str | None,
        summary: str | None,
        symbol: str,
        company_name: str | None = None,
        industry: str | None = None,
    ) -> float:
        text = f"{title or ''} {summary or ''}".lower()
        clean_symbol = normalize_symbol(symbol).lower()
        score = 0.0
        if clean_symbol and re.search(rf"(?<![a-z0-9]){re.escape(clean_symbol)}(?![a-z0-9])", text):
            score += 0.45
        if company_name:
            words = [word for word in re.split(r"\W+", company_name.lower()) if len(word) >= 3]
            if words and any(word in text for word in words[:6]):
                score += 0.25
        if industry:
            words = [word for word in re.split(r"\W+", industry.lower()) if len(word) >= 4]
            if words and any(word in text for word in words[:4]):
                score += 0.08
        keywords = (
            "kết quả kinh doanh",
            "báo cáo tài chính",
            "lợi nhuận",
            "doanh thu",
            "cổ tức",
            "triển vọng",
            "rủi ro",
            "đại hội cổ đông",
            "nghị quyết",
            "lãnh đạo",
        )
        score += min(0.22, 0.04 * sum(1 for keyword in keywords if keyword in text))
        return round(min(score, 1.0), 3)

    def inclusion_reason(self, *, reliability: float, relevance: float, freshness: float) -> str:
        parts = []
        if reliability >= 0.9:
            parts.append("nguồn có độ tin cậy cao")
        elif reliability >= 0.75:
            parts.append("nguồn tài chính Việt Nam uy tín")
        else:
            parts.append("nguồn chỉ dùng làm bối cảnh")
        if relevance >= 0.7:
            parts.append("liên quan trực tiếp tới mã/doanh nghiệp")
        elif relevance >= 0.45:
            parts.append("có tín hiệu liên quan")
        if freshness >= 0.7:
            parts.append("còn tương đối mới")
        return "; ".join(parts)

    def _age_score(self, published_at: datetime, *, long_lived: bool) -> float:
        value = published_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        age_days = max(0, (datetime.now(timezone.utc) - value.astimezone(timezone.utc)).days)
        if age_days <= 30:
            return 1.0
        if age_days <= 180:
            return 0.75
        if long_lived and age_days <= 730:
            return 0.65
        if age_days <= 730:
            return 0.45
        return 0.3 if long_lived else 0.2
