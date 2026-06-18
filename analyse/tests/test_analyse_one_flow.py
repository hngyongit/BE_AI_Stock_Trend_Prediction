from analyse.config.settings import Settings
from analyse.services.watchlist_service import WatchlistService


def test_watchlist_limits_to_five_symbols():
    service = WatchlistService(Settings(MAX_WATCHLIST_SYMBOLS=5))
    symbols = ["FPT", "CMG", "MWG", "HPG", "VCB", "SSI"]
    assert service.limit_symbols(symbols) == ["FPT", "CMG", "MWG", "HPG", "VCB"]


def test_watchlist_normalizes_and_validates_symbol():
    service = WatchlistService(Settings(MAX_WATCHLIST_SYMBOLS=5))
    allowed = service.limit_symbols(["FPT", "CMG"])
    ok, symbol = service.validate_symbol_allowed(" fpt ", allowed)
    assert ok is True
    assert symbol == "FPT"
