class VietstockCrawlerError(Exception):
    """Base exception for crawler errors."""


class ConfigurationError(VietstockCrawlerError):
    """Raised when required runtime configuration is missing or invalid."""


class VietstockPageError(VietstockCrawlerError):
    """Raised when Vietstock returns an invalid, stale, or unexpected page."""


class GoogleSheetsError(VietstockCrawlerError):
    """Raised when Google Sheets integration fails."""
