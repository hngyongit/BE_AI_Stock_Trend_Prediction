import pytest

from vietstock_crawler.utils.url_utils import (
    is_valid_company_profile_url,
    make_bctt_url,
    make_company_url,
    make_stats_url,
    normalize_slug_value,
)


def test_normalize_slug_value():
    assert normalize_slug_value("https://finance.vietstock.vn/FPT-ctcp-fpt.htm") == "FPT-ctcp-fpt"


def test_make_urls():
    assert make_stats_url("fpt").endswith("/FPT/thong-ke-giao-dich.htm")
    assert make_bctt_url("fpt").endswith("/FPT/tai-chinh.htm?tab=BCTT")
    assert make_company_url("FPT", "FPT-ctcp-fpt") == "https://finance.vietstock.vn/FPT-ctcp-fpt.htm"


def test_reject_auxiliary_profile_url():
    assert not is_valid_company_profile_url("https://finance.vietstock.vn/FPT/thong-ke-giao-dich.htm")
    with pytest.raises(ValueError):
        make_company_url("FPT", "FPT/thong-ke-giao-dich")
