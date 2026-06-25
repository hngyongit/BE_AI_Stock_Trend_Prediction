import asyncio

from analyse.config.settings import Settings
from analyse.services.report_service import ReportService


class FailingBackendClient:
    async def get_stock_analysis_data(self, **kwargs):
        raise RuntimeError("backend unavailable")


class CompanyAdapter:
    async def fetch(self, symbol: str, exchange: str | None = None):
        return {
            "company_name": f"Doanh nghiệp {symbol}",
            "exchange": exchange or "HOSE",
            "industry_level_2": "Tổ chức tín dụng",
            "source": "CafeF thông tin doanh nghiệp",
            "source_url": f"https://cafef.vn/du-lieu/hose/{symbol.lower()}-ban-lanh-dao-so-huu.chn",
            "status": "partial",
        }


class FailingCafeFFinancialAdapter:
    async def fetch(self, symbol: str, exchange: str | None = None):
        raise RuntimeError("cafef financial unavailable")


class VietstockFinancialAdapter:
    async def fetch(self, symbol: str):
        return {
            "source": "Vietstock Finance BCTC",
            "source_url": f"https://finance.vietstock.vn/{symbol}/tai-chinh.htm?tab=BCTT",
            "status": "success",
            "periods": [{"period": "Q1/2026", "eps": 3000, "pe": 8.5, "pb": 1.4, "roe": 19.2}],
        }


def test_peer_enrichment_tries_next_source_and_writes_specific_missing_notes(tmp_path):
    settings = Settings(
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        ENABLE_PEER_WEB_ENRICHMENT=True,
        PEER_WEB_ENRICHMENT_TIMEOUT_MS=1000,
    )
    service = ReportService(settings=settings, backend_client=FailingBackendClient())
    service.cafef_company_adapter = CompanyAdapter()
    service.cafef_financial_adapter = FailingCafeFFinancialAdapter()
    service.vietstock_financial_adapter = VietstockFinancialAdapter()
    peer = {
        "symbol": "BID",
        "company": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam",
        "source": "Vietstock Finance",
        "source_url": "https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm",
        "verified_row_evidence": "stock_link",
    }

    enriched, attempts = asyncio.run(service._enrich_single_peer(peer, "HOSE", user_token="request-token"))

    assert enriched["pe"] == 8.5
    assert enriched["pb"] == 1.4
    assert enriched["roe"] == 19.2
    assert "P/B" not in enriched["missing_metrics"]
    assert "ROE" not in enriched["missing_metrics"]
    assert "Chưa đủ chỉ tiêu định lượng" not in str(enriched)
    assert [attempt["source"] for attempt in attempts] == [
        "Backend analysis-data",
        "Vietstock Finance BCTC",
    ]
