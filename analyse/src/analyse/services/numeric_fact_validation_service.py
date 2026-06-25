from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import math
import re
from typing import Any

from analyse.utils.debug_scrub import scrub_debug_payload, scrub_debug_text
from analyse.utils.symbol_utils import normalize_symbol


@dataclass
class NumericFactValidationIssue:
    path: str
    value: Any
    reason: str
    action: str
    source: str | None = None


@dataclass
class NumericFactValidationResult:
    payload: dict[str, Any]
    issues: list[NumericFactValidationIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _NumericToken:
    text: str
    value: float
    start: int
    end: int


class NumericFactValidationService:
    """Conservative guardrail for exact numeric facts in LLM-controlled report sections."""

    WARNING_MESSAGE = (
        "Một số số liệu định lượng do mô hình tạo ra đã được bỏ qua hoặc đánh dấu cần kiểm chứng "
        "vì chưa có nguồn dữ liệu đối chiếu."
    )
    QUALITATIVE_REPLACEMENT = "số liệu cần kiểm chứng"
    ACTION_NUMERIC_NOTE = "Số liệu định lượng do mô hình nêu chưa có nguồn đối chiếu; cần dùng dữ liệu gốc để xác nhận."

    _NUMERIC_TOKEN_RE = re.compile(
        r"(?<![\w/])[-+]?\d+(?:[.,]\d+)*(?:\s*(?:%|tỷ|nghìn tỷ|triệu|vnd|vnđ|đồng|x|lần))?",
        re.IGNORECASE,
    )
    _SENSITIVE_WORDS = (
        "giá",
        "mục tiêu",
        "target",
        "vnd",
        "vnđ",
        "đồng",
        "doanh thu",
        "lợi nhuận",
        "profit",
        "revenue",
        "margin",
        "biên",
        "eps",
        "p/e",
        "pe",
        "p/b",
        "pb",
        "roe",
        "roa",
        "định giá",
        "valuation",
        "vốn hóa",
        "market cap",
        "thanh khoản",
        "volume",
        "khối lượng",
        "score",
        "điểm",
        "confidence",
        "tin cậy",
        "xác suất",
        "probability",
        "tăng trưởng",
        "growth",
        "tỷ trọng",
        "position",
        "stop",
        "dừng lỗ",
        "%",
        "tỷ",
    )
    _SENSITIVE_PATH_PARTS = (
        "price",
        "target",
        "valuation",
        "revenue",
        "profit",
        "margin",
        "eps",
        "pe",
        "pb",
        "roe",
        "roa",
        "score",
        "confidence",
        "probability",
        "volume",
        "liquidity",
        "market_cap",
        "price_zone",
        "position_size",
        "stop_loss",
        "quantitative",
        "evidence_table",
        "executive_forecast",
    )
    _SOURCE_SUMMARY_KEYS = {
        "latest_market",
        "price_history",
        "momentum",
        "bctc_3q",
        "financials",
        "financials_merged",
        "financial_source_contributions",
        "financial_conflicts",
        "financial_cross_checks",
        "cafef_financial_contribution",
        "financial_backfill_report",
        "financial_balance",
        "hose_market_context",
        "market_general_context",
        "market_context_debug",
        "industry_peer_context",
        "same_industry_recommendation",
        "data_coverage",
        "scores",
        "investment_plan",
        "source_backed_evidence",
        "report_presentation",
    }
    _VALIDATION_ROOTS = (
        ("strengths",),
        ("weaknesses",),
        ("system_decision", "reasons"),
        ("data_quality_notes",),
        ("llm_executive_forecast",),
        ("llm_quantitative_signal_summary",),
        ("llm_risk_map",),
        ("llm_evidence_table",),
        ("llm_scenarios",),
        ("action_plan",),
        ("investment_plan", "action_table"),
        ("scenarios",),
        ("forecast_scenarios",),
        ("checklist",),
        ("scenario_matrix",),
        ("report_presentation", "executive_summary"),
        ("report_presentation", "action_table", "rows"),
        ("report_presentation", "scenario_table", "rows"),
        ("report_presentation", "checklist", "items"),
    )

    def validate_summary(
        self,
        *,
        summary: dict[str, Any],
        source_payload: dict[str, Any] | None = None,
        allowed_numeric_paths: set[str] | None = None,
    ) -> NumericFactValidationResult:
        payload = deepcopy(summary) if isinstance(summary, dict) else {}
        issues: list[NumericFactValidationIssue] = []
        allowed_numbers = self._collect_allowed_numbers(payload, source_payload or {})
        allowed_paths = allowed_numeric_paths or set()

        for root in self._VALIDATION_ROOTS:
            if not self._path_exists(payload, root):
                continue
            value = self._get_path(payload, root)
            validated = self._validate_value(
                value,
                path=self._format_path(root),
                issues=issues,
                allowed_numbers=allowed_numbers,
                allowed_numeric_paths=allowed_paths,
                source="llm_or_forecast_section",
            )
            self._set_path(payload, root, validated)

        warnings = [self.WARNING_MESSAGE] if issues else []
        return NumericFactValidationResult(payload=payload, issues=issues, warnings=warnings)

    def build_debug_payload(self, *, symbol: str, result: NumericFactValidationResult) -> dict[str, Any]:
        clean_symbol = normalize_symbol(symbol) or "UNKNOWN"
        return scrub_debug_payload(
            {
                "symbol": clean_symbol,
                "issue_count": len(result.issues),
                "issues": [self._debug_issue(issue) for issue in result.issues],
                "warnings": result.warnings,
            }
        )

    def _validate_value(
        self,
        value: Any,
        *,
        path: str,
        issues: list[NumericFactValidationIssue],
        allowed_numbers: set[float],
        allowed_numeric_paths: set[str],
        source: str,
    ) -> Any:
        if self._path_allowed(path, allowed_numeric_paths):
            return value

        if isinstance(value, dict):
            return {
                key: self._validate_value(
                    item,
                    path=f"{path}.{key}",
                    issues=issues,
                    allowed_numbers=allowed_numbers,
                    allowed_numeric_paths=allowed_numeric_paths,
                    source=source,
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._validate_value(
                    item,
                    path=f"{path}[{index}]",
                    issues=issues,
                    allowed_numbers=allowed_numbers,
                    allowed_numeric_paths=allowed_numeric_paths,
                    source=source,
                )
                for index, item in enumerate(value)
            ]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not self._is_sensitive_numeric_field(path):
                return value
            if self._is_supported_number(float(value), allowed_numbers):
                return value
            issues.append(
                NumericFactValidationIssue(
                    path=path,
                    value=value,
                    reason="unsupported_llm_numeric",
                    action="set_null",
                    source=source,
                )
            )
            return None
        if isinstance(value, str):
            return self._validate_text(value, path=path, issues=issues, allowed_numbers=allowed_numbers, source=source)
        return value

    def _validate_text(
        self,
        value: str,
        *,
        path: str,
        issues: list[NumericFactValidationIssue],
        allowed_numbers: set[float],
        source: str,
    ) -> str:
        if not self._has_sensitive_context(value, path):
            return value

        unsupported = [
            token
            for token in self._numeric_tokens(value)
            if not self._is_supported_number(token.value, allowed_numbers)
        ]
        if not unsupported:
            return value

        action = "replaced_numeric_text"
        replacement = self._replace_tokens(value, unsupported, self.QUALITATIVE_REPLACEMENT)
        if self._is_action_numeric_path(path):
            replacement = self.ACTION_NUMERIC_NOTE
            action = "replaced_with_verification_note"

        issues.append(
            NumericFactValidationIssue(
                path=path,
                value=value,
                reason="unsupported_llm_numeric",
                action=action,
                source=source,
            )
        )
        return replacement

    def _collect_allowed_numbers(self, summary: dict[str, Any], source_payload: dict[str, Any]) -> set[float]:
        allowed: set[float] = set()
        self._collect_numbers(source_payload, allowed)
        safe_summary = {
            key: value
            for key, value in summary.items()
            if key in self._SOURCE_SUMMARY_KEYS and key != "report_presentation"
        }
        self._collect_numbers(safe_summary, allowed)

        presentation = summary.get("report_presentation")
        if isinstance(presentation, dict):
            safe_presentation = {
                key: presentation.get(key)
                for key in ("quick_overview", "market_context_view", "financial_table", "data_coverage", "coverage_rows", "score_cards")
                if key in presentation
            }
            self._collect_numbers(safe_presentation, allowed)
        return allowed

    def _collect_numbers(self, value: Any, allowed: set[float]) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            numeric = float(value)
            if math.isfinite(numeric):
                self._add_allowed_number(allowed, numeric)
            return
        if isinstance(value, dict):
            for item in value.values():
                self._collect_numbers(item, allowed)
            return
        if isinstance(value, list):
            for item in value:
                self._collect_numbers(item, allowed)

    def _add_allowed_number(self, allowed: set[float], numeric: float) -> None:
        rounded = round(numeric, 6)
        allowed.add(rounded)
        if 0 <= abs(numeric) <= 1:
            allowed.add(round(numeric * 100, 6))

    def _numeric_tokens(self, text: str) -> list[_NumericToken]:
        tokens: list[_NumericToken] = []
        for match in self._NUMERIC_TOKEN_RE.finditer(text):
            if self._is_date_or_period_token(text, match.start(), match.end()):
                continue
            numeric = self._parse_number(match.group(0))
            if numeric is None:
                continue
            tokens.append(_NumericToken(match.group(0), numeric, match.start(), match.end()))
        return tokens

    def _parse_number(self, token: str) -> float | None:
        cleaned = re.sub(r"(?i)(nghìn tỷ|tỷ|triệu|vnd|vnđ|đồng|%|x|lần)", "", token)
        cleaned = cleaned.replace(" ", "").strip()
        if not cleaned:
            return None
        sign = ""
        if cleaned[0] in "+-":
            sign = cleaned[0]
            cleaned = cleaned[1:]
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            parts = cleaned.split(",")
            if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
                cleaned = "".join(parts)
            else:
                cleaned = cleaned.replace(",", ".")
        elif "." in cleaned:
            parts = cleaned.split(".")
            if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
                cleaned = "".join(parts)
        try:
            numeric = float(sign + cleaned)
        except ValueError:
            return None
        return numeric if math.isfinite(numeric) else None

    def _is_supported_number(self, value: float, allowed_numbers: set[float]) -> bool:
        if not math.isfinite(value):
            return False
        for allowed in allowed_numbers:
            if math.isclose(value, allowed, rel_tol=0.0001, abs_tol=0.01):
                return True
        return False

    def _has_sensitive_context(self, text: str, path: str) -> bool:
        if not self._numeric_tokens(text):
            return False
        lower_text = text.lower()
        lower_path = path.lower()
        if any(part in lower_path for part in self._SENSITIVE_PATH_PARTS):
            return True
        return any(word in lower_text for word in self._SENSITIVE_WORDS)

    def _is_sensitive_numeric_field(self, path: str) -> bool:
        lower_path = path.lower()
        if (
            "probability_pct" in lower_path
            and "llm_scenarios" not in lower_path
            and ("scenario_matrix" in lower_path or "scenario_table" in lower_path or "forecast_scenarios" in lower_path)
        ):
            return False
        return any(part in lower_path for part in self._SENSITIVE_PATH_PARTS)

    def _is_action_numeric_path(self, path: str) -> bool:
        lower = path.lower()
        return any(part in lower for part in ("price_zone", "position_size", "stop_loss"))

    def _is_date_or_period_token(self, text: str, start: int, end: int) -> bool:
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        if before in {"/", "-"} or after in {"/", "-"}:
            return True
        window = text[max(0, start - 3) : min(len(text), end + 6)]
        if re.search(r"(?i)q[1-4]\s*/\s*\d{4}", window):
            return True
        token = text[start:end].strip()
        numeric = self._parse_number(token)
        if numeric is not None and numeric.is_integer() and 1900 <= int(numeric) <= 2100:
            return True
        return False

    def _replace_tokens(self, text: str, tokens: list[_NumericToken], replacement: str) -> str:
        result = text
        for token in sorted(tokens, key=lambda item: item.start, reverse=True):
            result = result[: token.start] + replacement + result[token.end :]
        return result

    def _path_allowed(self, path: str, allowed_numeric_paths: set[str]) -> bool:
        if path in allowed_numeric_paths:
            return True
        return any(pattern.endswith(".*") and path.startswith(pattern[:-2]) for pattern in allowed_numeric_paths)

    def _path_exists(self, payload: dict[str, Any], path: tuple[str, ...]) -> bool:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        return True

    def _get_path(self, payload: dict[str, Any], path: tuple[str, ...]) -> Any:
        current: Any = payload
        for key in path:
            current = current[key]
        return current

    def _set_path(self, payload: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
        current: Any = payload
        for key in path[:-1]:
            current = current[key]
        current[path[-1]] = value

    def _format_path(self, path: tuple[str, ...]) -> str:
        return "summary." + ".".join(path)

    def _debug_issue(self, issue: NumericFactValidationIssue) -> dict[str, Any]:
        payload = asdict(issue)
        if payload.get("reason") == "unsupported_llm_numeric":
            payload["value"] = "<redacted>"
            return payload
        if isinstance(payload.get("value"), str):
            payload["value"] = re.sub(
                r"(?i)authorization:\s*bearer\s*<redacted>",
                "<redacted>",
                scrub_debug_text(payload["value"]),
            )
        return payload
