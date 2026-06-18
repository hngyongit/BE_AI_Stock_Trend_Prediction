from __future__ import annotations

from typing import Iterable


def normalize_symbol(symbol: str | None) -> str:
    return (symbol or "").strip().upper()


def normalize_symbols(symbols: Iterable[str | None]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        clean = normalize_symbol(symbol)
        if clean and clean not in seen:
            normalized.append(clean)
            seen.add(clean)
    return normalized
