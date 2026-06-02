from vietstock_crawler.utils.number_utils import normalize_number, sanitize_share_volume


def test_normalize_number_vietnamese_decimal():
    assert normalize_number("1.234,56") == 1234.56
    assert normalize_number("1.234") == 1234.0
    assert normalize_number("1,23%") == 1.23


def test_normalize_number_negative_parentheses():
    assert normalize_number("(1.234,5)") == -1234.5


def test_sanitize_share_volume_rejects_small_date_like_values():
    assert sanitize_share_volume(27) is None
    assert sanitize_share_volume(999) is None
    assert sanitize_share_volume(1000) == 1000
