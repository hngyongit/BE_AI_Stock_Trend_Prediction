from vietstock_crawler.utils.text_utils import clean_config_text, normalize_text, strip_accents


def test_strip_accents():
    assert strip_accents("Đặng Thị Hồng") == "Dang Thi Hong"


def test_normalize_text():
    assert normalize_text("Lợi nhuận sau thuế  Q1/2026") == "loi nhuan sau thue q1/2026"


def test_clean_config_text():
    assert clean_config_text(None) == ""
    assert clean_config_text(" nan ") == ""
    assert clean_config_text(" FPT ") == "FPT"
