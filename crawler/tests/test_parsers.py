from vietstock_crawler.parsers.common import extract_latest_period_label, get_line_value_after_label, html_to_lines
from vietstock_crawler.parsers.trading_stats_parser import extract_period_price_change_raw
from vietstock_crawler.utils.date_utils import parse_quarter_suffix


def test_quarter_parse():
    assert parse_quarter_suffix("Quý 1/2026") == "Q1_2026"
    assert parse_quarter_suffix("Q4_2025") == "Q4_2025"


def test_html_to_lines_and_value_after_label():
    html = "<html><body><p>Doanh thu thuần</p><p>1.234,56</p></body></html>"
    lines = html_to_lines(html)
    assert lines == ["Doanh thu thuần", "1.234,56"]
    assert get_line_value_after_label(lines, ["Doanh thu thuần"]) == 1234.56


def test_extract_period_price_change_raw():
    lines = ["Biến động giá", "+1.200 (+5,50%)", "Cao nhất", "10.000"]
    value, pct = extract_period_price_change_raw(lines)
    assert value.startswith("'")
    assert pct.startswith("'")


def test_extract_latest_period_label_from_html():
    html = "<table><tr><th>Chỉ tiêu</th><th>Q4/2025</th><th>Q1/2026</th></tr></table>"
    assert extract_latest_period_label(html) in {"Q1/2026", "Q4/2025", ""}
