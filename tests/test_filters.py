from datetime import datetime

from ea_alert.filters import COUNTRY_TO_CURRENCY, indicator_matches
from ea_alert.models import JST, KIND_INDICATOR, Event


def make_event(country="米国", importance=3):
    return Event(
        kind=KIND_INDICATOR,
        datetime_jst=datetime(2026, 7, 31, 21, 30, tzinfo=JST),
        time_known=True,
        country=country,
        title="テスト指標",
        importance=importance,
    )


CURRENCIES = ["USD", "JPY", "EUR", "GBP"]


def test_mapping_covers_gaikaex_countries():
    assert COUNTRY_TO_CURRENCY["米国"] == "USD"
    assert COUNTRY_TO_CURRENCY["日本"] == "JPY"
    assert COUNTRY_TO_CURRENCY["ユーロ"] == "EUR"
    assert COUNTRY_TO_CURRENCY["ドイツ"] == "EUR"
    assert COUNTRY_TO_CURRENCY["フランス"] == "EUR"
    assert COUNTRY_TO_CURRENCY["イギリス"] == "GBP"


def test_matches_target_currency_and_importance():
    assert indicator_matches(make_event("米国", 3), CURRENCIES, min_importance=2)
    assert indicator_matches(make_event("ドイツ", 2), CURRENCIES, min_importance=2)


def test_rejects_low_importance():
    assert not indicator_matches(make_event("米国", 1), CURRENCIES, min_importance=2)


def test_rejects_non_target_country():
    assert not indicator_matches(make_event("トルコ", 3), CURRENCIES, min_importance=2)
    assert not indicator_matches(make_event("南アフリカ", 3), CURRENCIES, min_importance=2)


def test_rejects_unknown_country():
    assert not indicator_matches(make_event("未知の国", 3), CURRENCIES, min_importance=2)
