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
        confidence = self._confidence(components, periods, price_history)

        return {
            **components,
            "risk_label": self._risk_label(risk),
            "overall_score": overall,
            "overall_label": self._overall_label(overall),
            "score_confidence": confidence,
            "score_explanations": explanations,
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
            explanations.append("Valuation: thiếu P/E hợp lệ hoặc P/E là outlier.")

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
            explanations.append("Valuation: thiếu P/B hợp lệ.")

        if not scores:
            explanations.append("Valuation: dùng điểm trung tính do thiếu dữ liệu định giá.")
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
            explanations.append("Quality: thiếu ROE.")
        if ros is not None:
            scores.append(self._higher_is_better(ros, [(3, 30), (8, 55), (15, 75), (25, 90)], 25))
        if roaa is not None:
            scores.append(self._higher_is_better(roaa, [(1, 35), (3, 60), (5, 78), (8, 90)], 20))
        if profit is not None:
            scores.append(75 if profit > 0 else 20)
        else:
            explanations.append("Quality: thiếu lợi nhuận sau thuế trong BCTC.")
        if len(periods) >= 3:
            scores.append(70)
        elif periods:
            scores.append(55)
            explanations.append("Quality: số kỳ BCTC còn mỏng.")
        else:
            scores.append(40)
            explanations.append("Quality: chưa có BCTC để kiểm tra chất lượng lợi nhuận.")
        return self._round_score(mean(scores))

    def _growth_score(self, periods: list[dict[str, Any]], explanations: list[str]) -> int:
        if len(periods) < 2:
            explanations.append("Growth: cần ít nhất 2 kỳ BCTC để tính tăng trưởng.")
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
            explanations.append(f"Growth: {label} kỳ mới nhất so với kỳ trước khoảng {change_pct:.1f}%.")

        if not growth_scores:
            explanations.append("Growth: thiếu revenue/profit đủ để tính tăng trưởng.")
            return 50
        return self._round_score(mean(growth_scores))

    def _momentum_score(self, price_history: list[dict[str, Any]], explanations: list[str]) -> int:
        closes = [value for value in (self._num(item, "close", "close_price") for item in price_history) if value is not None]
        if len(closes) < 2 or closes[0] == 0:
            explanations.append("Momentum: thiếu lịch sử giá đủ dài.")
            return 50
        change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100
        explanations.append(f"Momentum: biến động giá trong chuỗi Backend khoảng {change_pct:.1f}%.")
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
            explanations.append("Liquidity: thiếu volume mới nhất.")
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
            explanations.append("Size: thiếu market_cap; dùng điểm trung tính.")
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
            explanations.append("Risk: thiếu beta.")

        closes = [value for value in (self._num(item, "close", "close_price") for item in price_history) if value is not None]
        if len(closes) >= 3:
            returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1]]
            volatility = self._stddev(returns) * math.sqrt(252) * 100 if returns else 0
            drawdown = self._max_drawdown(closes)
            risk_parts.append(self._higher_is_better(volatility, [(15, 30), (25, 50), (35, 68), (50, 85)], 95))
            risk_parts.append(self._higher_is_better(abs(drawdown), [(5, 25), (10, 45), (20, 65), (35, 85)], 95))
        else:
            risk_parts.append(50)
            explanations.append("Risk: thiếu chuỗi giá đủ dài để tính volatility/drawdown.")

        regime = str(market.get("regime") or "").lower()
        if regime == "risk_off":
            risk_parts.append(75)
            explanations.append("Risk: thị trường chung đang ở trạng thái risk_off.")
        elif regime == "risk_on":
            risk_parts.append(35)
        elif market:
            risk_parts.append(50)
        else:
            risk_parts.append(55)
            explanations.append("Risk: thiếu market context.")

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

    def _confidence(self, components: dict[str, int], periods: list[dict[str, Any]], price_history: list[dict[str, Any]]) -> float:
        confidence = 0.35
        if periods:
            confidence += 0.25
        if len(periods) >= 3:
            confidence += 0.15
        if len(price_history) >= 2:
            confidence += 0.15
        if all(value != 50 for value in components.values()):
            confidence += 0.10
        return round(min(confidence, 1.0), 2)

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
