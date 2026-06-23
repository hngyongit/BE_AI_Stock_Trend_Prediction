import json

from analyse.services.presentation_contract import normalize_percent_score
from analyse.services.presentation_contract import sanitize_data_source_statuses
from analyse.services.presentation_contract import sanitize_source_detail_for_user
from analyse.services.presentation_contract import to_user_facing_source_name
from analyse.services.summary_service import SummaryService


def test_normalize_percent_score_handles_ratio_percent_and_missing():
    assert normalize_percent_score(0.7) == 70
    assert normalize_percent_score(70) == 70
    assert normalize_percent_score(1) == 100
    assert normalize_percent_score(None) is None


def test_data_confidence_score_card_uses_0_100_meter_contract():
    cards = SummaryService()._score_cards(
        {
            "valuation_score": 68,
            "quality_score": 60,
            "growth_score": 50,
            "momentum_score": 55,
            "liquidity_score": 65,
            "size_score": 70,
            "risk_score": 45,
            "score_confidence": 0.7,
            "score_explanation_map": {},
        }
    )
    confidence_card = next(card for card in cards if card["key"] == "data_confidence")

    assert confidence_card["score"] == 70
    assert confidence_card["meter_percent"] == 70
    assert confidence_card["display_value"] == "70%"
    assert confidence_card["unit"] == "%"
    assert confidence_card["scale"] == "0-100"
    assert confidence_card["score"] != 0.7


def test_source_names_are_user_facing():
    assert to_user_facing_source_name("Backend /Api/Watchlists") == "Danh sách theo dõi cá nhân"
    assert to_user_facing_source_name("Backend /Api/Stocks/:Symbol/Analysis-Data") == "Dữ liệu giá và thanh khoản"
    assert to_user_facing_source_name("backend_api") == "Dữ liệu hệ thống"


def test_source_details_are_sanitized_for_users():
    raw_sources = [
        {"name": "Backend /api/watchlists", "type": "backend_api", "status": "success", "detail": "/api/watchlists"},
        {
            "name": "Backend /api/stocks/:symbol/analysis-data",
            "type": "backend_api",
            "status": "success",
            "detail": "exchange=HOSE; quarters=6; chartRange=3m",
        },
        {
            "name": "CafeF BCTC",
            "type": "external_financial",
            "status": "partial",
            "detail": "https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn; periods=0",
        },
        {
            "name": "Vietstock peer cùng ngành",
            "type": "external_peer",
            "status": "success",
            "detail": "https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm; page_loaded=true; tables_found=3; grid_rows_found=0; peer_rows_found=9; normalized_peers=9",
        },
        {"name": "Report HTML file", "type": "filesystem", "status": "disabled", "detail": "options.renderHtml=false"},
    ]

    clean_sources = sanitize_data_source_statuses(raw_sources)
    serialized = json.dumps(clean_sources, ensure_ascii=False)

    for forbidden in (
        "backend_api",
        "/api/watchlists",
        "page_loaded=true",
        "tables_found=3",
        "periods=0",
        "https://",
        "http://",
        "Report HTML file",
        "File HTML",
    ):
        assert forbidden not in serialized

    cafef = next(source for source in clean_sources if source["name"] == "CafeF tài chính")
    assert cafef["status"] == "insufficient"
    assert cafef["status_label"] == "Chưa đủ dữ liệu"
    assert "CafeF chưa cung cấp đủ kỳ tài chính" in cafef["summary"]

    peer = next(source for source in clean_sources if source["name"] == "Vietstock peer cùng ngành")
    assert peer["detail"] == "Đã ghi nhận 9 mã peer cùng nhóm ngành để phục vụ so sánh."


def test_cafef_financial_skipped_source_is_user_facing_without_vietstock_claim():
    clean_sources = sanitize_data_source_statuses(
        [
            {
                "name": "CafeF BCTC",
                "type": "external_financial",
                "status": "skipped",
                "detail": "reason=rate_limit_backoff",
            }
        ]
    )

    assert clean_sources == [
        {
            "name": "CafeF tài chính",
            "type": "financial",
            "category": "Báo cáo tài chính",
            "status": "skipped",
            "status_label": "Bỏ qua",
            "summary": "CafeF tài chính không được gọi do cấu hình hoặc chính sách giới hạn nguồn ngoài.",
            "detail": "CafeF tài chính không được gọi do cấu hình, lựa chọn người dùng hoặc chính sách giới hạn nguồn ngoài.",
            "source_type": "financial",
            "debug_detail": None,
        }
    ]


def test_sanitize_source_detail_rewrites_known_technical_details():
    assert sanitize_source_detail_for_user(
        {"name": "Backend /api/stocks/:symbol/analysis-data", "type": "backend_api", "detail": "exchange=HOSE; quarters=6; chartRange=3m"}
    ) == "Đã dùng để tính động lượng, thanh khoản và một phần điểm định lượng."
    assert sanitize_source_detail_for_user(
        {
            "name": "Vietstock peer cùng ngành",
            "detail": "https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm; page_loaded=true; tables_found=3; grid_rows_found=0; peer_rows_found=9; normalized_peers=9",
        }
    ) == "Đã ghi nhận 9 mã peer cùng nhóm ngành để phục vụ so sánh."
    assert sanitize_source_detail_for_user(
        {"name": "CafeF BCTC", "detail": "https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn; periods=0"}
    ) == "Báo cáo vẫn dùng nguồn BCTC đã chuẩn hóa khác nếu có."
