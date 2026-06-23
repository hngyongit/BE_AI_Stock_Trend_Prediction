from __future__ import annotations

import math
from statistics import mean
from typing import Any


class ScoringService:
    """Tính điểm định lượng minh bạch từ dữ liệu Backend đã chuẩn hóa."""

    VALID_RISK_LABELS = ("Thấp", "Trung bình", "Cao", "Rất cao")
    VALID_OVERALL_LABELS = ("Yếu", "Trung tính", "Khá tích cực", "Tích cực")

    def build_placeholder_scores(self, stock_detail: dict[str, Any]) -> dict[str, Any]:
        return self.build_scores(stock_detail)

    def build_scores(self, stock_detail: dict[str, Any]) -> dict[str, Any]:
        latest = self._dict(stock_detail.get("latest_market") or stock_detail.get("latestMarket") or stock_detail.get("latest_price"))
        price_history = self._list(stock_detail.get("price_history") or stock_detail.get("priceHistory"))
        financials = self._dict(stock_detail.get("financials"))
        periods = self._list(financials.get("periods") if financials else stock_detail.get("financials"))
        market = self._dict(stock_detail.get("hose_market_context") or stock_detail.get("market_overview") or stock_detail.get("hoseMarketContext"))
        peer_context = self._dict(stock_detail.get("industry_peer_context") or stock_detail.get("industryPeerContext"))
        peers = self._list(peer_context.get("peers"))
        research_context = self._dict(stock_detail.get("external_research_context") or stock_detail.get("externalResearchContext"))
        research_items = self._list(research_context.get("items"))
        data_quality = self._dict(stock_detail.get("data_quality") or stock_detail.get("dataQuality"))

        explanations: list[str] = []
        valuation = self._valuation_score(latest, explanations)
        quality = self._quality_score(latest, periods, explanations)
        growth = self._growth_score(periods, explanations)
        momentum = self._momentum_score(price_history, explanations)
        liquidity = self._liquidity_score(latest, price_history, explanations)
        size = self._size_score(latest, explanations)
        risk = self._risk_score(latest, price_history, market, explanations)

        components = {
            "valuation_score": valuation,
            "quality_score": quality,
            "growth_score": growth,
            "momentum_score": momentum,
            "liquidity_score": liquidity,
            "size_score": size,
            "risk_score": risk,
        }
        overall = self._overall_score(components)
        confidence = self._confidence(
            components=components,
            latest=latest,
            periods=periods,
            price_history=price_history,
            market=market,
            peers=peers,
            research_items=research_items,
            data_quality=data_quality,
        )

        return {
            **components,
            "risk_label": self._risk_label(risk),
            "overall_score": overall,
            "overall_label": self._overall_label(overall),
            "score_confidence": confidence,
            "score_explanations": explanations,
            "score_explanation_map": self._score_explanation_map(
                latest=latest,
                periods=periods,
                price_history=price_history,
                market=market,
                peers=peers,
                research_items=research_items,
                data_quality=data_quality,
                components=components,
            ),
        }

    def _valuation_score(self, latest: dict[str, Any], explanations: list[str]) -> int:
        scores: list[float] = []
        pe = self._num(latest, "pe", "pe_ratio")
        forward_pe = self._num(latest, "forward_pe", "forwardPe")
        pb = self._num(latest, "pb", "pb_ratio")
        roe = self._num(latest, "roe")

        if pe is not None and 0 < pe < 120:
            scores.append(self._lower_is_better(pe, [(8, 92), (12, 82), (18, 68), (25, 52), (40, 35)], 18))
        else:
            explanations.append("Định giá: chưa có P/E hợp lệ hoặc P/E có dấu hiệu ngoại lệ, nên chưa thể xem đây là tín hiệu định giá chắc chắn.")

        if forward_pe is not None and 0 < forward_pe < 120:
            scores.append(self._lower_is_better(forward_pe, [(8, 90), (12, 80), (18, 65), (25, 50), (40, 35)], 18))

        if pb is not None and pb > 0:
            pb_score = self._lower_is_better(pb, [(1, 88), (2, 74), (3, 58), (5, 40), (8, 25)], 15)
            if roe is not None and roe >= 15:
                pb_score = min(100, pb_score + 8)
            elif roe is not None and roe < 8:
                pb_score = max(0, pb_score - 10)
            scores.append(pb_score)
        else:
            explanations.append("Định giá: chưa có P/B hợp lệ để đối chiếu với giá trị sổ sách.")

        if not scores:
            explanations.append("Định giá: dùng điểm trung tính vì dữ liệu định giá chưa đủ.")
            return 50
        return self._round_score(mean(scores))

    def _quality_score(self, latest: dict[str, Any], periods: list[dict[str, Any]], explanations: list[str]) -> int:
        scores: list[float] = []
        roe = self._num(latest, "roe")
        ros = self._num(latest, "ros")
        roaa = self._num(latest, "roaa", "roa")
        latest_period = periods[0] if periods else {}
        profit = self._num(latest_period, "profit_after_tax", "parent_profit")

        if roe is not None:
            scores.append(self._higher_is_better(roe, [(5, 30), (10, 50), (15, 70), (20, 85), (30, 95)], 20))
        else:
            explanations.append("Chất lượng: thiếu ROE nên đánh giá hiệu quả vốn còn hạn chế.")
        if ros is not None:
            scores.append(self._higher_is_better(ros, [(3, 30), (8, 55), (15, 75), (25, 90)], 25))
        if roaa is not None:
            scores.append(self._higher_is_better(roaa, [(1, 35), (3, 60), (5, 78), (8, 90)], 20))
        if profit is not None:
            scores.append(75 if profit > 0 else 20)
        else:
            explanations.append("Chất lượng: thiếu lợi nhuận sau thuế trong BCTC, cần kiểm tra thêm chất lượng lợi nhuận.")
        if len(periods) >= 3:
            scores.append(70)
        elif periods:
            scores.append(55)
            explanations.append("Chất lượng: số kỳ BCTC còn mỏng nên độ tin cậy của đánh giá chưa cao.")
        else:
            scores.append(40)
            explanations.append("Chất lượng: chưa có BCTC để kiểm tra chất lượng lợi nhuận và bảng cân đối.")
        return self._round_score(mean(scores))

    def _growth_score(self, periods: list[dict[str, Any]], explanations: list[str]) -> int:
        if len(periods) < 2:
            explanations.append("Tăng trưởng: cần ít nhất hai kỳ BCTC để đánh giá xu hướng doanh thu và lợi nhuận.")
            return 50

        latest, previous = periods[0], periods[1]
        growth_scores: list[float] = []
        for label, key in (("doanh thu", "revenue"), ("lợi nhuận sau thuế", "profit_after_tax"), ("lợi nhuận cổ đông mẹ", "parent_profit")):
            current = self._num(latest, key)
            prior = self._num(previous, key)
            if current is None or prior in (None, 0):
                continue
            change_pct = ((current - prior) / abs(prior)) * 100
            growth_scores.append(self._growth_to_score(change_pct))
            direction = "tăng" if change_pct > 0 else "giảm" if change_pct < 0 else "đi ngang"
            explanations.append(f"Tăng trưởng: {label} kỳ mới nhất {direction} khoảng {abs(change_pct):.1f}% so với kỳ liền trước; cần kiểm tra động lực cốt lõi nếu biến động lớn.")

        if not growth_scores:
            explanations.append("Tăng trưởng: thiếu doanh thu hoặc lợi nhuận đủ để tính xu hướng đáng tin cậy.")
            return 50
        return self._round_score(mean(growth_scores))

    def _momentum_score(self, price_history: list[dict[str, Any]], explanations: list[str]) -> int:
        closes = [value for value in (self._num(item, "close", "close_price") for item in price_history) if value is not None]
        if len(closes) < 2 or closes[0] == 0:
            explanations.append("Động lượng giá: chuỗi giá chưa đủ dài để đánh giá xu hướng.")
            return 50
        change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100
        direction = "tích cực" if change_pct > 0 else "tiêu cực" if change_pct < 0 else "đi ngang"
        explanations.append(f"Động lượng giá: giá biến động {change_pct:.1f}% trong chuỗi dữ liệu hiện có, tạm xem là tín hiệu {direction}.")
        return self._round_score(self._growth_to_score(change_pct))

    def _liquidity_score(self, latest: dict[str, Any], price_history: list[dict[str, Any]], explanations: list[str]) -> int:
        close = self._num(latest, "close_price", "close")
        volume = self._num(latest, "volume")
        volumes = [value for value in (self._num(item, "volume") for item in price_history) if value is not None]
        avg_volume = mean(volumes) if volumes else None

        scores: list[float] = []
        if volume is not None:
            scores.append(self._higher_is_better(volume, [(100_000, 25), (500_000, 45), (1_000_000, 60), (5_000_000, 78), (10_000_000, 90)], 95))
        else:
            explanations.append("Thanh khoản: thiếu volume mới nhất nên cần thận trọng khi đọc biến động giá.")
        if close is not None and volume is not None:
            trading_value = close * volume
            scores.append(self._higher_is_better(trading_value, [(10_000_000_000, 30), (50_000_000_000, 50), (100_000_000_000, 65), (500_000_000_000, 82), (1_000_000_000_000, 92)], 98))
        if avg_volume is not None:
            scores.append(self._higher_is_better(avg_volume, [(100_000, 25), (500_000, 45), (1_000_000, 60), (5_000_000, 78), (10_000_000, 90)], 95))
        if not scores:
            return 50
        return self._round_score(mean(scores))

    def _size_score(self, latest: dict[str, Any], explanations: list[str]) -> int:
        market_cap = self._num(latest, "market_cap", "marketCap")
        if market_cap is None:
            explanations.append("Quy mô: thiếu market cap nên dùng điểm trung tính cho yếu tố ổn định quy mô.")
            return 50
        return self._round_score(self._higher_is_better(market_cap, [(1_000, 30), (10_000, 50), (50_000, 70), (100_000, 82), (300_000, 92)], 98))

    def _risk_score(
        self,
        latest: dict[str, Any],
        price_history: list[dict[str, Any]],
        market: dict[str, Any],
        explanations: list[str],
    ) -> int:
        risk_parts: list[float] = []
        beta = self._num(latest, "beta")
        if beta is not None:
            risk_parts.append(self._higher_is_better(beta, [(0.6, 25), (0.9, 40), (1.1, 55), (1.4, 72), (1.8, 88)], 95))
        else:
            risk_parts.append(50)
            explanations.append("Rủi ro: thiếu beta nên chưa đánh giá đầy đủ độ nhạy với thị trường.")

        closes = [value for value in (self._num(item, "close", "close_price") for item in price_history) if value is not None]
        if len(closes) >= 3:
            returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1]]
            volatility = self._stddev(returns) * math.sqrt(252) * 100 if returns else 0
            drawdown = self._max_drawdown(closes)
            risk_parts.append(self._higher_is_better(volatility, [(15, 30), (25, 50), (35, 68), (50, 85)], 95))
            risk_parts.append(self._higher_is_better(abs(drawdown), [(5, 25), (10, 45), (20, 65), (35, 85)], 95))
        else:
            risk_parts.append(50)
            explanations.append("Rủi ro: chuỗi giá chưa đủ dài để tính volatility và drawdown đáng tin cậy.")

        regime = str(market.get("regime") or "").lower()
        if regime == "risk_off":
            risk_parts.append(75)
            explanations.append("Rủi ro: bối cảnh thị trường chung đang risk_off nên cần giảm mức tự tin của tín hiệu.")
        elif regime == "risk_on":
            risk_parts.append(35)
        elif market:
            risk_parts.append(50)
        else:
            risk_parts.append(55)
            explanations.append("Rủi ro: thiếu market context nên chưa đánh giá đầy đủ tác động từ thị trường chung.")

        foreign_net = self._num(latest, "foreign_net")
        if foreign_net is not None and foreign_net < 0:
            risk_parts.append(60)
        elif foreign_net is not None and foreign_net > 0:
            risk_parts.append(42)

        return self._round_score(mean(risk_parts))

    def _overall_score(self, components: dict[str, int]) -> int:
        weighted = (
            components["valuation_score"] * 0.20
            + components["quality_score"] * 0.20
            + components["growth_score"] * 0.15
            + components["momentum_score"] * 0.15
            + components["liquidity_score"] * 0.10
            + components["size_score"] * 0.10
            + (100 - components["risk_score"]) * 0.10
        )
        return self._round_score(weighted)

    def _confidence(
        self,
        *,
        components: dict[str, int],
        latest: dict[str, Any],
        periods: list[dict[str, Any]],
        price_history: list[dict[str, Any]],
        market: dict[str, Any],
        peers: list[dict[str, Any]],
        research_items: list[dict[str, Any]],
        data_quality: dict[str, Any],
    ) -> float:
        confidence = 0.25
        if latest:
            confidence += 0.18
        if len(price_history) >= 2:
            confidence += 0.12
        if periods:
            confidence += 0.16
        if len(periods) >= 3:
            confidence += 0.10
        if market:
            confidence += 0.08
        if peers:
            confidence += 0.07
        if research_items:
            confidence += 0.04
        if all(value != 50 for value in components.values()):
            confidence += 0.05

        warnings = " ".join(str(item).lower() for item in self._list_any(data_quality.get("warnings")))
        missing = self._list_any(data_quality.get("missing_fields") or data_quality.get("missingFields"))

        cap = 1.0
        if not peers:
            cap = min(cap, 0.75)
        if "đơn vị" in warnings or "unit" in warnings or "market_cap" in warnings:
            cap = min(cap, 0.80)
        if not research_items:
            cap = min(cap, 0.85)
        if not periods:
            cap = min(cap, 0.60)
        if not latest:
            cap = min(cap, 0.55)
        if missing and len(missing) >= 4:
            cap = min(cap, 0.70)
        if len(self._list_any(data_quality.get("warnings"))) >= 3:
            cap = min(cap, 0.70)

        return round(min(confidence, cap), 2)

    def _risk_label(self, score: int) -> str:
        if score <= 30:
            return "Thấp"
        if score <= 60:
            return "Trung bình"
        if score <= 80:
            return "Cao"
        return "Rất cao"

    def _overall_label(self, score: int) -> str:
        if score <= 39:
            return "Yếu"
        if score <= 59:
            return "Trung tính"
        if score <= 74:
            return "Khá tích cực"
        return "Tích cực"

    def _score_explanation_map(
        self,
        *,
        latest: dict[str, Any],
        periods: list[dict[str, Any]],
        price_history: list[dict[str, Any]],
        market: dict[str, Any],
        peers: list[dict[str, Any]],
        research_items: list[dict[str, Any]],
        data_quality: dict[str, Any],
        components: dict[str, int],
    ) -> dict[str, str]:
        pe = self._num(latest, "pe", "pe_ratio")
        forward_pe = self._num(latest, "forward_pe", "forwardPe")
        pb = self._num(latest, "pb", "pb_ratio")
        roe = self._num(latest, "roe")
        ros = self._num(latest, "ros")
        roaa = self._num(latest, "roaa", "roa")
        volume = self._num(latest, "volume")
        close = self._num(latest, "close_price", "close")
        market_cap = self._num(latest, "market_cap", "marketCap")
        beta = self._num(latest, "beta")

        latest_period = periods[0] if periods else {}
        previous_period = periods[1] if len(periods) > 1 else {}
        revenue_growth = self._period_growth(latest_period, previous_period, "revenue")
        profit_growth = self._period_growth(latest_period, previous_period, "profit_after_tax")
        price_change = self._price_change(price_history)

        return {
            "valuation_score": (
                "Định giá được đọc từ P/E, forward P/E, P/B và điều chỉnh bởi ROE. "
                f"P/E={self._fmt(pe)}, forward P/E={self._fmt(forward_pe)}, P/B={self._fmt(pb)}, ROE={self._fmt(roe)}."
            ),
            "quality_score": (
                "Chất lượng phản ánh ROE, biên lợi nhuận, ROAA và lợi nhuận sau thuế trong BCTC. "
                f"ROE={self._fmt(roe)}, ROS={self._fmt(ros)}, ROAA={self._fmt(roaa)}, số kỳ BCTC hợp lệ={len(periods)}."
            ),
            "growth_score": (
                "Tăng trưởng dựa trên thay đổi doanh thu và lợi nhuận sau thuế giữa các kỳ tài chính gần nhất. "
                f"Tăng trưởng doanh thu={self._fmt(revenue_growth)}%, tăng trưởng LNST={self._fmt(profit_growth)}%."
            ),
            "momentum_score": (
                "Động lượng giá dùng biến động giá trong chuỗi chart và cần đọc cùng xác nhận thanh khoản. "
                f"Biến động giá kỳ chart={self._fmt(price_change)}%."
            ),
            "liquidity_score": (
                "Thanh khoản dựa trên khối lượng giao dịch mới nhất và giá trị giao dịch ước tính. "
                f"Volume={self._fmt(volume)}, giá đóng cửa={self._fmt(close)}."
            ),
            "size_score": (
                "Quy mô phản ánh vốn hóa thị trường nếu dữ liệu có sẵn; quy mô lớn thường giúp ổn định hơn nhưng không đảm bảo hiệu quả đầu tư. "
                f"Market cap={self._fmt(market_cap)}."
            ),
            "risk_score": (
                "Rủi ro kết hợp beta, volatility/drawdown từ chuỗi giá, bối cảnh thị trường và các khoảng trống dữ liệu. "
                f"Beta={self._fmt(beta)}, trạng thái thị trường={market.get('regime') or 'chưa xác minh'}, điểm rủi ro={components.get('risk_score')}."
            ),
            "data_confidence": (
                "Tỷ lệ tin cậy dữ liệu xét độ phủ giá, BCTC, bối cảnh thị trường, peer và nguồn nghiên cứu bên ngoài. "
                f"Peer={len(peers)} mã, tin tức/nghiên cứu={len(research_items)} mục, cảnh báo dữ liệu={len(self._list_any(data_quality.get('warnings')))}."
            ),
        }

    def _period_growth(self, latest: dict[str, Any], previous: dict[str, Any], key: str) -> float | None:
        current = self._num(latest, key)
        prior = self._num(previous, key)
        if current is None or prior in (None, 0):
            return None
        return round((current - prior) / abs(prior) * 100, 1)

    def _price_change(self, price_history: list[dict[str, Any]]) -> float | None:
        closes = [value for value in (self._num(item, "close", "close_price") for item in price_history) if value is not None]
        if len(closes) < 2 or closes[0] == 0:
            return None
        return round((closes[-1] - closes[0]) / closes[0] * 100, 1)

    def _fmt(self, value: Any) -> str:
        if value is None:
            return "chưa xác minh"
        if isinstance(value, float):
            return f"{value:,.2f}".rstrip("0").rstrip(".")
        return str(value)

    def _growth_to_score(self, change_pct: float) -> float:
        if change_pct <= -30:
            return 15
        if change_pct <= -10:
            return 35
        if change_pct < 0:
            return 45
        if change_pct < 5:
            return 55
        if change_pct < 15:
            return 68
        if change_pct < 30:
            return 82
        return 92

    def _lower_is_better(self, value: float, thresholds: list[tuple[float, float]], fallback: float) -> float:
        for limit, score in thresholds:
            if value <= limit:
                return score
        return fallback

    def _higher_is_better(self, value: float, thresholds: list[tuple[float, float]], fallback: float) -> float:
        score = fallback
        for limit, threshold_score in thresholds:
            if value <= limit:
                return threshold_score
            score = threshold_score
        return score

    def _stddev(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        avg = mean(values)
        return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))

    def _max_drawdown(self, closes: list[float]) -> float:
        peak = closes[0]
        max_drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            if peak:
                max_drawdown = min(max_drawdown, (close - peak) / peak * 100)
        return max_drawdown

    def _round_score(self, value: float) -> int:
        return int(max(0, min(100, round(value))))

    def _num(self, data: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = data.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        return None

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def _list_any(self, value: Any) -> list[Any]:
        return value if isinstance(value, list) else []
