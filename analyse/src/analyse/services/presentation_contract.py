from __future__ import annotations

import re
from typing import Any


STATUS_LABELS = {
    "available": "Đã ghi nhận",
    "success": "Đã ghi nhận",
    "partial": "Ghi nhận một phần",
    "insufficient": "Chưa đủ dữ liệu",
    "failed": "Chưa lấy được",
    "missing": "Chưa xác minh",
    "not_configured": "Chưa cấu hình",
    "disabled": "Chưa cấu hình",
    "skipped": "Bỏ qua",
    "not_implemented": "Chưa triển khai",
}

TECHNICAL_DETAIL_MARKERS = (
    "/api/",
    "backend_api",
    "page_loaded",
    "tables_found",
    "grid_rows_found",
    "peer_rows_found",
    "normalized_peers",
    "periods=",
    "fields=",
    "leadership_rows=",
    "ownership_rows=",
    "exchange=",
    "quarters=",
    "chartrange=",
    "https://",
    "http://",
)


def normalize_percent_score(value: Any) -> int | None:
    if value is None:
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    if numeric != numeric:
        return None
    if 0 <= numeric <= 1:
        numeric = numeric * 100

    return max(0, min(100, round(numeric)))


def normalize_score_0_100(value: Any) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return max(0, min(100, round(numeric)))


def display_percent_value(value: Any) -> str | None:
    score = normalize_percent_score(value)
    return f"{score}%" if score is not None else None


def to_user_facing_source_name(raw_name: str, raw_type: str | None = None) -> str:
    text = str(raw_name or "").strip()
    type_text = str(raw_type or "").strip()
    key = _source_key(text)
    type_key = _source_key(type_text)
    mapping = {
        "backend /api/watchlists": "Danh sách theo dõi cá nhân",
        "backend /api/stocks/:symbol/analysis-data": "Dữ liệu giá và thanh khoản",
        "backend /api/stocks/{symbol}/analysis-data": "Dữ liệu giá và thanh khoản",
        "backend /api/stocks/:symbol/chart": "Chuỗi giá",
        "backend /api/stocks/{symbol}/chart": "Chuỗi giá",
        "backend /api/stocks/:symbol": "Hồ sơ cổ phiếu đã xác thực",
        "backend /api/stocks/{symbol}": "Hồ sơ cổ phiếu đã xác thực",
        "backend_api": "Dữ liệu hệ thống",
        "cafef_company": "CafeF thông tin doanh nghiệp",
        "cafef company overview": "CafeF thông tin doanh nghiệp",
        "cafef thông tin doanh nghiệp": "CafeF thông tin doanh nghiệp",
        "cafef_financial": "CafeF tài chính",
        "cafef bctc": "CafeF tài chính",
        "cafef tài chính": "CafeF tài chính",
        "vietstock_financial": "Vietstock Finance BCTC",
        "vietstock finance bctt": "Vietstock Finance BCTC",
        "vietstock finance bctc": "Vietstock Finance BCTC",
        "vietstock_peer": "Vietstock peer cùng ngành",
        "vietstock peer cùng ngành": "Vietstock peer cùng ngành",
        "external_research": "Tin tức và nghiên cứu bên ngoài",
        "external research": "Tin tức và nghiên cứu bên ngoài",
        "vietstock_cafef_google_news": "Tin tức và nghiên cứu bên ngoài",
        "official_disclosure": "Nguồn công bố chính thức",
        "nguồn công bố chính thức": "Nguồn công bố chính thức",
        "google_news_rss": "Google News",
        "google news rss": "Google News",
        "vietstock_via_google_news_rss": "Vietstock qua Google News",
        "cafef_via_google_news_rss": "CafeF qua Google News",
    }
    if key in mapping:
        return mapping[key]
    if type_key in mapping:
        return mapping[type_key]
    if key == "cafef":
        if any(marker in type_key for marker in ("financial", "bctc", "finance")):
            return "CafeF tài chính"
        if any(marker in type_key for marker in ("company", "profile", "overview", "ownership", "leadership")):
            return "CafeF thông tin doanh nghiệp"
        if any(marker in type_key for marker in ("research", "news", "rss")):
            return "CafeF qua Google News"
        return "CafeF thông tin doanh nghiệp"
    if key == "vietstock":
        if any(marker in type_key for marker in ("financial", "bctc", "finance")):
            return "Vietstock Finance BCTC"
        if any(marker in type_key for marker in ("peer", "industry", "comparison")):
            return "Vietstock peer cùng ngành"
        if any(marker in type_key for marker in ("research", "news", "rss")):
            return "Vietstock qua Google News"
        return "Vietstock Finance BCTC"
    if "/api/" in key or key.startswith("backend "):
        return "Dữ liệu hệ thống"
    return text or "Nguồn dữ liệu"


def sanitize_source_detail_for_user(source: Any) -> str:
    data = _source_dict(source)
    raw_name = data.get("name")
    raw_type = data.get("type") or data.get("source_type")
    name = to_user_facing_source_name(str(raw_name or ""), str(raw_type or ""))
    status = normalize_source_status(data)
    detail = str(data.get("detail") or "")
    detail_lower = detail.lower()

    if name == "Danh sách theo dõi cá nhân":
        return (
            "Nguồn dùng để xác minh mã được phép phân tích."
            if status == "success"
            else "Chưa xác minh được quyền phân tích mã từ danh sách theo dõi."
        )
    if name in {"Dữ liệu giá và thanh khoản", "Hồ sơ cổ phiếu đã xác thực", "Chuỗi giá"}:
        if status == "failed":
            return "Nguồn dữ liệu thị trường chưa phản hồi trong lần chạy này."
        if name == "Chuỗi giá":
            return "Đã dùng để đọc xu hướng giá gần nhất."
        return "Đã dùng để tính động lượng, thanh khoản và một phần điểm định lượng."
    if name == "CafeF thông tin doanh nghiệp":
        fields = _extract_int(detail, "fields")
        leadership = _extract_int(detail, "leadership_rows")
        ownership = _extract_int(detail, "ownership_rows")
        if status in {"insufficient", "failed"} or (fields == 0 and not leadership and not ownership):
            return "CafeF đã được kiểm tra nhưng chưa đủ hồ sơ doanh nghiệp, lãnh đạo hoặc sở hữu có thể chuẩn hóa."
        return "Dùng cho phần tổng quan doanh nghiệp, ban lãnh đạo hoặc sở hữu nếu trích xuất được."
    if name == "CafeF tài chính":
        periods = _extract_int(detail, "periods")
        filled = _extract_int(detail, "filled_count") or 0
        usable = _extract_int(detail, "usable_count") or 0
        if status == "skipped":
            return "CafeF tài chính không được gọi do cấu hình, lựa chọn người dùng hoặc chính sách giới hạn nguồn ngoài."
        if status == "failed":
            return "Báo cáo vẫn tiếp tục với các nguồn tài chính đã xác thực khác."
        if filled > 0:
            return f"CafeF đã bù {filled} chỉ tiêu/kỳ tài chính còn thiếu vào dữ liệu hợp nhất."
        if usable > 0:
            return f"CafeF cung cấp {usable} chỉ tiêu để đối chiếu, nhưng không ghi đè dữ liệu ưu tiên cao hơn."
        if periods == 0 or status == "insufficient":
            return "CafeF đã được kiểm tra nhưng không có chỉ tiêu tài chính đủ tin cậy để bù vào dữ liệu hợp nhất."
        return "CafeF tài chính được dùng để đối chiếu BCTC và chỉ số tài chính."
    if name == "Vietstock Finance BCTC":
        periods = _extract_int(detail, "periods")
        if status == "success" and (periods is None or periods > 0):
            return "Dùng cho bảng BCTC, định giá và xu hướng tài chính."
        if status == "partial" and periods and periods > 0:
            return "Dùng một phần cho chỉ số tài chính và cần đối chiếu thêm kỳ BCTC."
        return "Vietstock Finance chưa cung cấp đủ kỳ BCTC có thể chuẩn hóa trong lần chạy này."
    if name == "Vietstock peer cùng ngành":
        peers = _extract_int(detail, "normalized_peers")
        if peers is None:
            peers = _extract_int(detail, "peer_rows_found")
        if peers and peers > 0:
            return f"Đã ghi nhận {peers} mã peer cùng nhóm ngành để phục vụ so sánh."
        return "Nguồn đã được kiểm tra nhưng chưa đủ dòng peer cùng ngành dùng được."
    if name in {"Tin tức và nghiên cứu bên ngoài", "Google News", "Vietstock qua Google News", "CafeF qua Google News"}:
        items = _extract_int(detail, "items")
        if status == "success" and items is not None:
            return f"Đã ghi nhận {items} tin tức/nghiên cứu phù hợp; chỉ dùng làm bằng chứng ngữ cảnh."
        if status == "disabled":
            return "Nguồn tin tức/nghiên cứu bên ngoài chưa được bật cho lần chạy này."
        return "Chỉ dùng làm bằng chứng ngữ cảnh, không tạo số liệu tài chính mới."
    if name == "Nguồn công bố chính thức":
        return "Chỉ dùng các công bố/nguồn chính thống tìm được làm bằng chứng kiểm chứng, không tạo số liệu mới."
    if not _contains_technical_detail(detail_lower) and detail.strip():
        return detail.strip()
    return "Nguồn đã được đối chiếu ở mức phù hợp với dữ liệu hiện có."


def source_status_label(status: Any) -> str:
    return STATUS_LABELS.get(str(status or "").strip().lower(), "Cần kiểm tra")


def normalize_source_status(source: Any) -> str:
    data = _source_dict(source)
    status = str(data.get("status") or "").strip().lower() or "partial"
    raw_name = str(data.get("name") or "")
    raw_type = str(data.get("type") or data.get("source_type") or "")
    name = to_user_facing_source_name(raw_name, raw_type)
    detail = str(data.get("detail") or "")

    if status == "not_configured":
        status = "disabled"
    if name == "CafeF tài chính" and _extract_int(detail, "periods") == 0 and status not in {"failed", "disabled", "skipped"}:
        return "insufficient"
    if name == "Vietstock Finance BCTC" and _extract_int(detail, "periods") == 0 and status not in {"failed", "disabled"}:
        return "insufficient"
    if name == "Vietstock peer cùng ngành":
        peers = _extract_int(detail, "normalized_peers")
        if peers == 0 and status not in {"failed", "disabled"}:
            return "insufficient"
    if status == "available":
        return "success"
    if status == "missing":
        return "insufficient"
    if status in STATUS_LABELS:
        return status
    return "partial"


def sanitize_data_source_for_user(source: Any) -> dict[str, Any] | None:
    data = _source_dict(source)
    raw_name = str(data.get("name") or "")
    raw_type = str(data.get("type") or data.get("source_type") or "")
    if _is_report_file_source(raw_name, raw_type):
        return None

    name = to_user_facing_source_name(raw_name, raw_type)
    status = normalize_source_status(data)
    source_type = _source_type_for_user(name, raw_type)
    category = _source_category_for_user(name, source_type)
    summary = _source_summary_for_user(name, status, data)
    detail = sanitize_source_detail_for_user({**data, "name": name, "status": status, "type": source_type})

    row = {
        "name": name,
        "type": source_type,
        "category": category,
        "status": status,
        "status_label": source_status_label(status),
        "summary": summary,
        "detail": detail,
        "source_type": source_type,
        "debug_detail": None,
    }
    if data.get("evidence_count") is not None:
        row["evidence_count"] = data.get("evidence_count")
    if data.get("last_crawled_at") is not None:
        row["last_crawled_at"] = data.get("last_crawled_at")
    return row


def sanitize_data_source_statuses(sources: Any) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for source in sources:
        sanitized = sanitize_data_source_for_user(source)
        if not sanitized:
            continue
        key = (sanitized["name"], sanitized["status"], sanitized["detail"])
        if key in seen:
            continue
        result.append(sanitized)
        seen.add(key)
    return result


def build_data_source_debug_rows(raw_sources: Any, sanitized_sources: Any) -> list[dict[str, Any]]:
    raw_list = [_source_dict(source) for source in raw_sources] if isinstance(raw_sources, list) else []
    clean_list = sanitized_sources if isinstance(sanitized_sources, list) else []
    rows: list[dict[str, Any]] = []
    for raw in raw_list:
        sanitized = sanitize_data_source_for_user(raw)
        rows.append(
            {
                "raw_source_name": raw.get("name"),
                "raw_type": raw.get("type"),
                "raw_status": raw.get("status"),
                "raw_detail": raw.get("detail"),
                "sanitized_name": (sanitized or {}).get("name"),
                "sanitized_status": (sanitized or {}).get("status"),
                "sanitized_detail": (sanitized or {}).get("detail"),
                "included_in_user_sources": bool(sanitized and sanitized in clean_list),
                "technical_debug": {
                    "raw": raw,
                },
            }
        )
    return rows


def _source_dict(source: Any) -> dict[str, Any]:
    if isinstance(source, dict):
        return dict(source)
    model_dump = getattr(source, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _source_key(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _extract_int(text: Any, key: str) -> int | None:
    match = re.search(rf"(?:^|[;\s]){re.escape(key)}\s*=\s*(\d+)", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _contains_technical_detail(detail_lower: str) -> bool:
    return any(marker in detail_lower for marker in TECHNICAL_DETAIL_MARKERS)


def _is_report_file_source(name: str, source_type: str) -> bool:
    text = _source_key(name)
    type_text = _source_key(source_type)
    return type_text == "filesystem" or text in {"report markdown file", "report html file", "file markdown", "file html"}


def _source_type_for_user(name: str, raw_type: str) -> str:
    if name == "Danh sách theo dõi cá nhân":
        return "backend"
    if name in {"Dữ liệu giá và thanh khoản", "Hồ sơ cổ phiếu đã xác thực", "Chuỗi giá", "Dữ liệu hệ thống"}:
        return "backend"
    if name == "CafeF thông tin doanh nghiệp":
        return "company_profile"
    if name in {"CafeF tài chính", "Vietstock Finance BCTC"}:
        return "financial"
    if name == "Vietstock peer cùng ngành":
        return "peer"
    if name in {"Tin tức và nghiên cứu bên ngoài", "Google News", "Vietstock qua Google News", "CafeF qua Google News"}:
        return "external_research"
    if name == "Nguồn công bố chính thức":
        return "official_disclosure"
    clean = _source_key(raw_type)
    if clean and not _contains_technical_detail(clean):
        return clean.replace(" ", "_")
    return "source"


def _source_category_for_user(name: str, source_type: str) -> str:
    if name == "Danh sách theo dõi cá nhân":
        return "Dữ liệu người dùng"
    if source_type == "backend" or name in {"Dữ liệu giá và thanh khoản", "Chuỗi giá"}:
        return "Dữ liệu thị trường"
    if source_type == "company_profile":
        return "Hồ sơ doanh nghiệp"
    if source_type == "financial":
        return "Báo cáo tài chính"
    if source_type == "peer":
        return "So sánh ngành"
    if source_type == "external_research":
        return "Bối cảnh thông tin"
    if source_type == "official_disclosure":
        return "Nguồn chính thống"
    return "Nguồn dữ liệu"


def _source_summary_for_user(name: str, status: str, source: dict[str, Any]) -> str:
    detail = str(source.get("detail") or "")
    if name == "Danh sách theo dõi cá nhân":
        return "Mã phân tích thuộc watchlists của người dùng." if status == "success" else "Chưa xác minh được watchlists của người dùng."
    if name in {"Dữ liệu giá và thanh khoản", "Hồ sơ cổ phiếu đã xác thực", "Chuỗi giá"}:
        return "Đã ghi nhận giá, khối lượng và chuỗi giá gần nhất." if status == "success" else "Dữ liệu thị trường chưa sẵn sàng đầy đủ."
    if name == "CafeF thông tin doanh nghiệp":
        return "Đã đối chiếu hồ sơ doanh nghiệp, ban lãnh đạo hoặc sở hữu." if status in {"success", "partial"} else "CafeF chưa cung cấp đủ hồ sơ doanh nghiệp có thể chuẩn hóa."
    if name == "CafeF tài chính":
        filled = _extract_int(detail, "filled_count") or 0
        usable = _extract_int(detail, "usable_count") or 0
        if status == "skipped":
            return "CafeF tài chính không được gọi do cấu hình hoặc chính sách giới hạn nguồn ngoài."
        if status == "failed":
            return "CafeF tài chính tải quá thời gian cho phép hoặc chưa phản hồi trong lần chạy này."
        if filled > 0:
            return "Đã ghi nhận dữ liệu tài chính từ CafeF để bổ sung/đối chiếu BCTC."
        if usable > 0:
            return "CafeF cung cấp một phần dữ liệu tài chính có thể đối chiếu."
        if status == "insufficient" or _extract_int(detail, "periods") == 0:
            return "CafeF chưa cung cấp đủ kỳ tài chính có thể chuẩn hóa trong lần chạy này."
        return "Đã đối chiếu thêm dữ liệu tài chính từ CafeF."
    if name == "Vietstock Finance BCTC":
        return "Đã ghi nhận các kỳ BCTC và chỉ số tài chính có thể chuẩn hóa." if status in {"success", "partial"} else "Vietstock Finance chưa cung cấp đủ kỳ BCTC trong lần chạy này."
    if name == "Vietstock peer cùng ngành":
        peers = _extract_int(detail, "normalized_peers") or _extract_int(detail, "peer_rows_found")
        if status in {"success", "partial"} and peers:
            return f"Đã ghi nhận {peers} doanh nghiệp cùng nhóm ngành để so sánh."
        return "Chưa đủ peer cùng ngành có thể chuẩn hóa trong lần chạy này."
    if name in {"Tin tức và nghiên cứu bên ngoài", "Google News", "Vietstock qua Google News", "CafeF qua Google News"}:
        return "Đã ghi nhận các tin tức/nghiên cứu phù hợp." if status == "success" else "Tin tức/nghiên cứu bên ngoài chưa đủ độ phủ."
    if name == "Nguồn công bố chính thức":
        return "Đã đối chiếu nguồn công bố chính thức phù hợp." if status in {"success", "partial"} else "Chưa tìm được nguồn công bố chính thức phù hợp trong lần chạy này."
    return "Nguồn dữ liệu đã được đối chiếu."
