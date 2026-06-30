"""Service for generating and verifying signed URLs for visualization datasets."""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from urllib.parse import urlencode

from analyse.config.settings import Settings, get_settings

ALLOWED_VISUALIZATION_TABLES: set[str] = {
    "prices",
    "financial_periods",
    "scores",
    "peers",
    "market_context",
    "ai_signals",
    "data_quality",
}


class VisualizationSignedUrlService:
    """Generate and verify secure signed URLs for visualization datasets.

    Uses HMAC-SHA256 with constant-time comparison for security.
    URLs expire after TTL specified in settings.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def generate_signed_dataset_url(
        self,
        symbol: str,
        exchange: str | None = None,
        chart_range: str | None = None,
        format: str = "json",
        ttl_seconds: int | None = None,
        dataset_id: str | None = None,
    ) -> str:
        """Generate a signed URL for fetching visualization dataset.

        Args:
            symbol: Stock symbol (e.g., 'FPT')
            exchange: Stock exchange (e.g., 'HOSE')
            chart_range: Chart range (e.g., '1y', '3m')
            format: Response format ('json' or 'csv')
            ttl_seconds: URL validity in seconds (uses setting if None)

        Returns:
            Signed URL for visualization-datasets endpoint
        """
        if not str(self.settings.data_formulator_signed_url_secret or "").strip():
            raise ValueError("DATA_FORMULATOR_SIGNED_URL_SECRET not configured")

        format = str(format or "json").strip().lower()
        if format != "json":
            raise ValueError(f"Unsupported signed dataset format: {format}")
        ttl = ttl_seconds or self.settings.visualization_dataset_ttl_seconds

        symbol = str(symbol or "").strip().upper()
        exchange = str(exchange or "").strip().upper() or "HOSE"
        dataset_id = str(dataset_id or self._generate_dataset_id(symbol, exchange)).strip()
        expires = int(time.time()) + ttl

        signature = self._create_signature(
            dataset_id=dataset_id,
            format=format,
            expires=expires,
        )

        params = {
            "expires": expires,
            "signature": signature,
        }

        base_url = self.settings.analyse_api_base_url or f"http://localhost:{self.settings.analyse_port}"
        query_string = urlencode(params)
        return f"{base_url}/api/ai-reports/visualization-datasets/{dataset_id}.json?{query_string}"

    def generate_csv_download_url(
        self,
        symbol: str,
        exchange: str | None = None,
        table: str = "prices",
        ttl_seconds: int | None = None,
        dataset_id: str | None = None,
    ) -> str:
        """Generate a signed URL for downloading CSV table.

        Args:
            symbol: Stock symbol
            exchange: Stock exchange
            table: Table name ('prices', 'financial_periods', etc.)
            ttl_seconds: URL validity in seconds

        Returns:
            Signed CSV download URL
        """
        if not str(self.settings.data_formulator_signed_url_secret or "").strip():
            raise ValueError("DATA_FORMULATOR_SIGNED_URL_SECRET not configured")

        symbol = str(symbol or "").strip().upper()
        exchange = str(exchange or "").strip().upper() or "HOSE"
        table = str(table or "").strip().lower()
        if table not in ALLOWED_VISUALIZATION_TABLES:
            raise ValueError(f"Unsupported table for signed CSV URL: {table}")
        ttl = ttl_seconds or self.settings.visualization_dataset_ttl_seconds

        dataset_id = str(dataset_id or self._generate_dataset_id(symbol, exchange)).strip()
        expires = int(time.time()) + ttl

        signature = self._create_csv_signature(
            dataset_id=dataset_id,
            format="csv",
            table=table,
            expires=expires,
        )

        params = {
            "table": table,
            "expires": expires,
            "signature": signature,
        }

        base_url = self.settings.analyse_api_base_url or f"http://localhost:{self.settings.analyse_port}"
        query_string = urlencode(params)
        return f"{base_url}/api/ai-reports/visualization-datasets/{dataset_id}.csv?{query_string}"

    def verify_signature(
        self,
        dataset_id: str,
        format: str,
        expires: int,
        signature: str,
    ) -> tuple[bool, str | None]:
        """Verify a signed URL signature using constant-time comparison.

        Args:
            dataset_id: Dataset ID from URL
            symbol: Stock symbol
            exchange: Exchange code
            chart_range: Chart range parameter
            format: Response format
            expires: Expiry timestamp
            signature: Provided signature

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not str(self.settings.data_formulator_signed_url_secret or "").strip():
            return False, "Signed URL not configured (missing secret)"

        if not str(dataset_id or "").strip():
            return False, "Missing dataset_id"
        if format not in {"json", ""}:
            return False, "Unsupported format"
        # Check expiry first
        if int(time.time()) > expires:
            return False, f"Signed URL expired at {expires}"

        # Compute expected signature
        expected_signature = self._create_signature(
            dataset_id=dataset_id,
            format=format,
            expires=expires,
        )

        # Constant-time comparison
        is_valid = hmac.compare_digest(signature, expected_signature)
        if not is_valid:
            return False, "Invalid signature"

        return True, None

    def verify_csv_signature(
        self,
        dataset_id: str,
        format: str,
        table: str,
        expires: int,
        signature: str,
    ) -> tuple[bool, str | None]:
        """Verify a CSV download signature.

        Args:
            dataset_id: Dataset ID
            symbol: Stock symbol
            exchange: Exchange code
            table: Table name
            expires: Expiry timestamp
            signature: Provided signature

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not str(self.settings.data_formulator_signed_url_secret or "").strip():
            return False, "Signed URL not configured (missing secret)"

        if not str(dataset_id or "").strip():
            return False, "Missing dataset_id"
        if format != "csv":
            return False, "Unsupported format"
        if table not in ALLOWED_VISUALIZATION_TABLES:
            return False, f"Invalid table: {table}"
        if int(time.time()) > expires:
            return False, f"Signed URL expired at {expires}"

        expected_signature = self._create_csv_signature(
            dataset_id=dataset_id,
            format=format,
            table=table,
            expires=expires,
        )

        is_valid = hmac.compare_digest(signature, expected_signature)
        if not is_valid:
            return False, "Invalid signature"

        return True, None

    def _create_signature(
        self,
        dataset_id: str,
        format: str,
        expires: int,
    ) -> str:
        """Create HMAC-SHA256 signature for dataset URL."""
        secret = str(self.settings.data_formulator_signed_url_secret or "")

        message = f"dataset_id={dataset_id}&format={format}&expires={expires}"

        signature = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    def _create_csv_signature(
        self,
        dataset_id: str,
        format: str,
        table: str,
        expires: int,
    ) -> str:
        """Create HMAC-SHA256 signature for CSV download."""
        secret = str(self.settings.data_formulator_signed_url_secret or "")

        message = f"dataset_id={dataset_id}&format={format}&table={table}&expires={expires}"

        signature = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    @staticmethod
    def _generate_dataset_id(symbol: str, exchange: str) -> str:
        """Generate a stable dataset ID from symbol and exchange.

        Uses timestamp and UU ID for uniqueness but deterministic for same symbol/exchange.
        """
        timestamp = int(time.time())
        dataset_id = f"{symbol}_{exchange}_{timestamp}_{uuid.uuid4().hex[:8]}"
        return dataset_id

    def generate_dataset_id(self, symbol: str, exchange: str | None = None) -> str:
        clean_symbol = str(symbol or "").strip().upper()
        clean_exchange = str(exchange or "").strip().upper() or "HOSE"
        return self._generate_dataset_id(clean_symbol, clean_exchange)

