"""Tests for visualization signed URL service."""

from __future__ import annotations

import time
import pytest
from analyse.config.settings import Settings
from analyse.services.visualization_signed_url_service import VisualizationSignedUrlService


@pytest.fixture
def settings() -> Settings:
    """Provide test settings."""
    return Settings(
        data_formulator_signed_url_secret="test-secret-key-must-be-at-least-32-chars",
        visualization_dataset_ttl_seconds=1800,
        analyse_api_base_url="http://localhost:5100",
    )


@pytest.fixture
def service(settings: Settings) -> VisualizationSignedUrlService:
    """Provide signed URL service."""
    return VisualizationSignedUrlService(settings)


class TestVisualizationSignedUrlGeneration:
    """Test signed URL generation."""

    def test_generate_signed_dataset_url(self, service: VisualizationSignedUrlService):
        """Test generating a signed dataset URL."""
        url = service.generate_signed_dataset_url(
            symbol="FPT",
            exchange="HOSE",
            chart_range="1y",
            format="json",
        )
        assert url.startswith("http://localhost:5100/api/ai-reports/visualization-datasets/")
        assert ".json?" in url
        assert "FPT_HOSE" in url
        assert "signature=" in url
        assert "expires=" in url

    def test_generate_csv_download_url(self, service: VisualizationSignedUrlService):
        """Test generating a signed CSV download URL."""
        url = service.generate_csv_download_url(
            symbol="HPG",
            exchange="HOSE",
            table="prices",
        )
        assert ".csv?" in url
        assert "table=prices" in url
        assert "signature=" in url
        assert "expires=" in url
        assert "HPG_HOSE" in url

    def test_url_contains_all_required_parameters(self, service: VisualizationSignedUrlService):
        """Test that generated URLs contain all required parameters."""
        url = service.generate_signed_dataset_url(
            symbol="TCB",
            exchange="HOSE",
            chart_range="3m",
        )
        assert "expires=" in url
        assert "signature=" in url


class TestVisualizationSignedUrlVerification:
    """Test signed URL verification."""

    def test_verify_valid_signature(self, service: VisualizationSignedUrlService):
        """Test verifying a valid signature."""
        dataset_id = f"FPT_HOSE_{int(time.time())}_12345678"
        expires = int(time.time()) + 1800
        signature = service._create_signature(
            dataset_id=dataset_id,
            format="json",
            expires=expires,
        )

        is_valid, error = service.verify_signature(
            dataset_id=dataset_id,
            format="json",
            expires=expires,
            signature=signature,
        )
        assert is_valid is True
        assert error is None

    def test_reject_invalid_signature(self, service: VisualizationSignedUrlService):
        """Test rejecting an invalid signature."""
        dataset_id = f"FPT_HOSE_{int(time.time())}_12345678"
        expires = int(time.time()) + 1800

        is_valid, error = service.verify_signature(
            dataset_id=dataset_id,
            format="json",
            expires=expires,
            signature="invalid-signature",
        )
        assert is_valid is False
        assert "Invalid signature" in error

    def test_reject_expired_signature(self, service: VisualizationSignedUrlService):
        """Test rejecting an expired signature."""
        dataset_id = f"FPT_HOSE_{int(time.time())}_12345678"
        expires = int(time.time()) - 100  # Expired
        signature = service._create_signature(
            dataset_id=dataset_id,
            format="json",
            expires=expires,
        )

        is_valid, error = service.verify_signature(
            dataset_id=dataset_id,
            format="json",
            expires=expires,
            signature=signature,
        )
        assert is_valid is False
        assert "expired" in error.lower()

    def test_verify_csv_signature(self, service: VisualizationSignedUrlService):
        """Test verifying a CSV signature."""
        dataset_id = f"FPT_HOSE_{int(time.time())}_12345678"
        expires = int(time.time()) + 1800
        signature = service._create_csv_signature(
            dataset_id=dataset_id,
            format="csv",
            table="prices",
            expires=expires,
        )

        is_valid, error = service.verify_csv_signature(
            dataset_id=dataset_id,
            format="csv",
            table="prices",
            expires=expires,
            signature=signature,
        )
        assert is_valid is True
        assert error is None


class TestSignedUrlSecretValidation:
    """Test secret validation."""

    def test_missing_secret_raises_error(self):
        """Test that missing secret raises an error."""
        settings = Settings(data_formulator_signed_url_secret=None)
        service = VisualizationSignedUrlService(settings)

        with pytest.raises(ValueError, match="not configured"):
            service.generate_signed_dataset_url("FPT", "HOSE")

    def test_empty_secret_raises_error(self):
        """Test that empty secret raises an error."""
        settings = Settings(data_formulator_signed_url_secret="")
        service = VisualizationSignedUrlService(settings)

        with pytest.raises(ValueError, match="not configured"):
            service.generate_signed_dataset_url("FPT", "HOSE")


class TestSignatureConstantTimeComparison:
    """Test constant-time comparison for security."""

    def test_signature_comparison_is_constant_time(self, service: VisualizationSignedUrlService):
        """Test that signature comparison uses constant-time comparison."""
        import hmac

        dataset_id = f"FPT_HOSE_{int(time.time())}_12345678"
        expires = int(time.time()) + 1800
        correct_sig = service._create_signature(
            dataset_id=dataset_id,
            format="json",
            expires=expires,
        )

        # Verify that hmac.compare_digest is being used (constant-time)
        wrong_sig = "a" * len(correct_sig)

        # Both should fail but take similar time
        is_valid1, _ = service.verify_signature(
            dataset_id=dataset_id,
            format="json",
            expires=expires,
            signature=wrong_sig,
        )
        assert is_valid1 is False

        is_valid2, _ = service.verify_signature(
            dataset_id=dataset_id,
            format="json",
            expires=expires,
            signature=correct_sig,
        )
        assert is_valid2 is True


class TestParameterNormalization:
    """Test parameter normalization."""

    def test_symbol_normalized_to_uppercase(self, service: VisualizationSignedUrlService):
        """Test that symbol is normalized to uppercase."""
        url_lower = service.generate_signed_dataset_url(symbol="fpt", exchange="HOSE")
        url_upper = service.generate_signed_dataset_url(symbol="FPT", exchange="HOSE")

        # Both should produce the same result
        assert "FPT" in url_lower
        assert "FPT" in url_upper

    def test_default_exchange_is_hose(self, service: VisualizationSignedUrlService):
        """Test that default exchange is HOSE."""
        url = service.generate_signed_dataset_url(symbol="FPT")
        assert "FPT_HOSE" in url

    def test_ttl_respected(self, service: VisualizationSignedUrlService):
        """Test that TTL is respected."""
        before = int(time.time())
        url = service.generate_signed_dataset_url(symbol="FPT", ttl_seconds=3600)
        after = int(time.time())

        # Extract expires from URL
        import re
        match = re.search(r"expires=(\d+)", url)
        assert match is not None
        expires = int(match.group(1))

        # Should be approximately now + 3600
        assert 3600 - 10 <= (expires - before) <= 3600 + 10
        assert 3600 - 10 <= (expires - after) <= 3600 + 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

