from __future__ import annotations

from typing import Any


class DataNormalizerService:
    """Skeleton chuan hoa du lieu backend/crawler truoc khi dua vao prompt."""

    def unwrap_backend_response(self, payload: Any) -> Any:
        """TODO: Xu ly wrapper { success, message, data } cua API Node.js."""
        if isinstance(payload, dict) and "success" in payload and "data" in payload:
            return payload.get("data")
        return payload

    def normalize_stock_data(self, payload: Any) -> dict[str, Any]:
        """
        TODO: Chuan hoa null, chuoi so, so dinh dang Viet Nam, percent, OHLCV,
        Mongoose ObjectId/date, du lieu tai chinh rong va crawl quality.
        """
        data = self.unwrap_backend_response(payload)
        return {
            "data": data,
            "metadata": {
                "qualityLevel": "MEDIUM",
                "missingFields": [],
                "notes": [
                    "Đây là kết quả chuẩn hóa placeholder; chưa có logic làm sạch dữ liệu chi tiết."
                ],
            },
        }

    def normalize_watchlist_data(self, payload: Any) -> dict[str, Any]:
        """TODO: Chuan hoa danh sach watchlist tu direct mode hoac backend fetch mode."""
        data = self.unwrap_backend_response(payload)
        return {
            "data": data,
            "metadata": {
                "qualityLevel": "MEDIUM",
                "missingFields": [],
                "notes": [
                    "Đây là kết quả chuẩn hóa watchlist placeholder."
                ],
            },
        }
