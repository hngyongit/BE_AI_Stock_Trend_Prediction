from __future__ import annotations

from copy import deepcopy

from analyse.utils.debug_scrub import REDACTED, safe_url_for_log, scrub_debug_payload, scrub_debug_text


def test_scrub_debug_payload_scrubs_nested_dict_without_mutating_input():
    payload = {
        "symbol": "FPT",
        "company_name": "CTCP FPT",
        "Authorization": "Bearer abc.def.ghi",
        "nested": {
            "OPENAI_API_KEY": "sk-proj-secretvalue123456",
            "source_label": "CafeF tài chính",
        },
    }
    original = deepcopy(payload)

    scrubbed = scrub_debug_payload(payload)

    assert payload == original
    assert scrubbed["symbol"] == "FPT"
    assert scrubbed["company_name"] == "CTCP FPT"
    assert scrubbed["nested"]["source_label"] == "CafeF tài chính"
    assert scrubbed["Authorization"] == REDACTED
    assert scrubbed["nested"]["OPENAI_API_KEY"] == REDACTED


def test_scrub_debug_payload_scrubs_nested_list():
    payload = [
        {"source_label": "Vietstock Finance BCTC", "refresh_token": "refresh-secret"},
        ["Bearer raw.token.value", {"jwt": "jwt-secret"}],
    ]

    scrubbed = scrub_debug_payload(payload)

    assert scrubbed[0]["source_label"] == "Vietstock Finance BCTC"
    assert scrubbed[0]["refresh_token"] == REDACTED
    assert scrubbed[1][0] == f"Bearer {REDACTED}"
    assert scrubbed[1][1]["jwt"] == REDACTED


def test_scrub_debug_text_removes_bearer_tokens_and_key_values():
    text = "Authorization: Bearer abc.def.ghi password=secret api_key=secret2"

    scrubbed = scrub_debug_text(text)

    assert "abc.def.ghi" not in scrubbed
    assert "secret" not in scrubbed
    assert scrubbed.count(REDACTED) >= 3


def test_safe_url_for_log_scrubs_sensitive_query_params_and_db_password():
    url = "mssql+pyodbc://user:db-secret@localhost/db?driver=ODBC&token=t1&api_key=k1&password=p1&symbol=FPT"

    scrubbed = safe_url_for_log(url)

    assert scrubbed is not None
    assert "db-secret" not in scrubbed
    assert "t1" not in scrubbed
    assert "k1" not in scrubbed
    assert "p1" not in scrubbed
    assert "symbol=FPT" in scrubbed


def test_scrub_preserves_non_sensitive_business_values():
    payload = {
        "symbol": "VCB",
        "company": "Ngân hàng TMCP Ngoại thương Việt Nam",
        "source_label": "Nguồn công bố chính thức",
        "source_url": "https://example.com/report?symbol=VCB",
    }

    assert scrub_debug_payload(payload) == payload
