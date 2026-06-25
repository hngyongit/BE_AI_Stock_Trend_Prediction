from analyse.utils.datetime_utils import format_percent_ratio


def test_format_percent_ratio_handles_ratios_and_percent_values():
    assert format_percent_ratio(0.6) == "60%"
    assert format_percent_ratio(0.75) == "75%"
    assert format_percent_ratio(1) == "100%"
    assert format_percent_ratio(60) == "60%"
    assert format_percent_ratio(None) == "Chưa xác minh"
